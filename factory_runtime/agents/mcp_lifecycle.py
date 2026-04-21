import asyncio
import logging
import signal
from pathlib import Path
from typing import Any

from factory_runtime.mcp_runtime import MCPRuntimeManager, RuntimeProfileName

logger = logging.getLogger(__name__)

FACTORY_DIRNAME = ".copilot/softwareFactoryVscode"
SERVER_URL_MAPPINGS: dict[str, tuple[str, str]] = {
    "mcp-memory": ("manifest_health_urls", "mcp-memory"),
    "mcp-agent-bus": ("manifest_health_urls", "mcp-agent-bus"),
    "mcp-github-ops": ("manifest_server_urls", "githubOps"),
    "mcp-search": ("manifest_server_urls", "search"),
    "mcp-filesystem": ("manifest_server_urls", "filesystem"),
}


class MCPBootloader:
    def __init__(
        self,
        workspace_root: Path,
        kill_mcps_on_exit: bool = False,
        force_rebuild_mcps: bool = False,
    ):
        self.workspace_root = workspace_root
        self.kill_mcps_on_exit = kill_mcps_on_exit
        self.force_rebuild_mcps = force_rebuild_mcps
        self._teardown_handled = False
        self.server_urls: dict[str, str] = {}
        self._factory_repo_root: Path | None = None
        self._env_file: Path | None = None
        self._runtime_manager: MCPRuntimeManager | None = None

    def setup_signal_handlers(self):
        """Phase 3.1: Graceful SIGINT Trapping."""
        loop = asyncio.get_event_loop()
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, self._handle_signal, sig)
        except NotImplementedError:
            # For Windows compatibility if needed
            signal.signal(signal.SIGINT, lambda s, f: self._handle_signal(s))
            signal.signal(signal.SIGTERM, lambda s, f: self._handle_signal(s))

    def _handle_signal(self, sig):
        if getattr(self, "_signal_handled", False):
            return
        self._signal_handled = True
        logger.info(f"\nReceived signal {sig}. Initiating graceful teardown...")

        loop = asyncio.get_event_loop()
        for task in asyncio.all_tasks(loop):
            task.cancel()

    async def initialize(self):
        """Initialize the canonical workspace runtime before FACTORY runs.

        This bootloader intentionally delegates lifecycle ownership to
        `scripts/factory_stack.py` so FACTORY issue runs follow the same generated
        `.factory.env` and runtime-manifest contract as the installed workspace.
        """
        logger.info(
            "Initializing MCP Bootloader via canonical factory_stack lifecycle..."
        )

        self._runtime_manager = self._build_runtime_manager()
        self._factory_repo_root = self._runtime_manager.resolve_factory_repo_root(
            self.workspace_root
        )
        self._env_file = self._runtime_manager.resolve_workspace_env_file(
            self.workspace_root,
            self._factory_repo_root,
        )

        snapshot = self._runtime_manager.build_workspace_snapshot(
            self.workspace_root,
            selected_profiles=(RuntimeProfileName.HARNESS_DEFAULT,),
        )
        readiness = self._require_snapshot_readiness(snapshot)

        if self.force_rebuild_mcps:
            logger.info(
                "Forcing canonical runtime rebuild for `%s`.",
                self._factory_repo_root,
            )
            try:
                self._runtime_manager.stop(
                    self._factory_repo_root,
                    env_file=self._env_file,
                )
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "Runtime stop before rebuild was not clean; continuing with rebuild: %s",
                    exc,
                )

        if self.force_rebuild_mcps or not readiness.ready:
            logger.info(
                "Canonical runtime preflight status is `%s`; reconciling with factory_stack.py start.",
                readiness.status.value,
            )
            self._runtime_manager.start(
                self._factory_repo_root,
                env_file=self._env_file,
                build=True,
                wait=True,
            )
            snapshot = self._runtime_manager.build_workspace_snapshot(
                self.workspace_root,
                selected_profiles=(RuntimeProfileName.HARNESS_DEFAULT,),
            )
            readiness = self._require_snapshot_readiness(snapshot)

        if not readiness.ready:
            raise RuntimeError(self._format_preflight_failure(readiness))

        self.server_urls = self._extract_server_urls(snapshot)
        logger.info("Pre-flight checks passed. All canonical MCP services are go.")

    def _build_runtime_manager(self) -> MCPRuntimeManager:
        return MCPRuntimeManager()

    def _require_snapshot_readiness(self, snapshot: Any) -> Any:
        readiness = getattr(snapshot, "readiness", None)
        if readiness is None:
            raise RuntimeError("Runtime snapshot did not include a readiness result.")
        return readiness

    def _extract_server_urls(self, snapshot: Any) -> dict[str, str]:
        server_urls: dict[str, str] = {}
        for server_name, (section_name, runtime_name) in SERVER_URL_MAPPINGS.items():
            section = getattr(snapshot, section_name, {})
            url = (
                str(section.get(runtime_name, "")).strip()
                if isinstance(section, dict)
                else ""
            )
            if not url:
                raise RuntimeError(
                    "Runtime preflight did not publish a URL for required MCP service "
                    f"`{server_name}`."
                )
            server_urls[server_name] = url
        return server_urls

    def _format_preflight_failure(self, readiness: Any) -> str:
        issues = [
            str(issue) for issue in getattr(readiness, "issues", ()) if str(issue)
        ]
        if not issues:
            issues = ["Unknown runtime preflight failure."]
        return (
            "FACTORY runtime failed preflight after canonical lifecycle reconciliation: "
            + " ".join(str(issue) for issue in issues)
        )

    def teardown(self):
        """Tear down the canonical runtime when explicitly requested."""
        if getattr(self, "_teardown_handled", False):
            return
        self._teardown_handled = True

        if self.kill_mcps_on_exit:
            logger.info("Stopping canonical MCP runtime (--kill-mcps-on-exit is set).")
            self._stop_containers()
        else:
            logger.info("Skipping orphan sweep. Containers will remain running.")

    def _stop_containers(self):
        """Teardown the canonical Docker compose services (stop and remove)."""
        if (
            not self._runtime_manager
            or not self._factory_repo_root
            or not self._env_file
        ):
            return
        try:
            self._runtime_manager.stop(
                self._factory_repo_root,
                env_file=self._env_file,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to tear down containers: {exc}")
