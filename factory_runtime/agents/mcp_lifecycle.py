import asyncio
import json
import logging
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)


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

        # We will populate these further in subsequent tasks
        self.compose_files = [
            "docker-compose.factory.yml",
            "docker-compose.repo-fundamentals-mcp.yml",
            "docker-compose.mcp-bash-gateway.yml",
            "docker-compose.mcp-github-ops.yml",
            "docker-compose.mcp-devops.yml",
            "docker-compose.mcp-offline-docs.yml",
        ]

        self.required_ports = [
            3011,  # bash
            3012,
            3013,
            3014,  # repo-fundamentals
            3015,
            3016,  # devops
            3017,  # offline-docs
            3018,  # github-ops
            3030,  # memory
            3031,  # agent-bus
        ]

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
        """Phase 1: Pre-Flight MCP Validation (Start / Boot Time)"""
        logger.info("Initializing MCP Bootloader...")
        reused = self._ensure_containers()
        self._wait_for_health_checks()

        if reused:
            # Phase 2.1: SQLite Integrity Check if reused
            self._check_sqlite_integrity()

        # Phase 2.2: Data Hydration
        self._hydrate_state()

        logger.info("Pre-flight checks passed. All MCPs are go.")

    def _get_compose_args(self) -> list[str]:
        args = []
        for f in self.compose_files:
            p = self.workspace_root / f
            if p.exists():
                args.extend(["-f", str(p)])
        return args

    def _ensure_containers(self) -> bool:
        """Starts or restarts the containers depending on the force_rebuild_mcps flag.
        Returns True if containers were reused, False if they were rebuilt.
        """
        compose_args = self._get_compose_args()
        if not compose_args:
            return False

        need_rebuild = self.force_rebuild_mcps

        if not need_rebuild:
            # Quick check if they are already running
            try:
                cmd = ["docker", "compose"] + compose_args + ["ps", "--format", "json"]
                result = subprocess.run(
                    cmd,
                    check=True,
                    timeout=120,
                    cwd=self.workspace_root,
                    capture_output=True,
                    text=True,
                )

                # If there's no output or it's empty array
                if not result.stdout.strip() or result.stdout.strip() == "[]":
                    need_rebuild = True
                else:
                    try:
                        containers = json.loads(result.stdout)
                        # Ensure there's a good count of containers running (rough heuristic)
                        running = [
                            c
                            for c in containers
                            if "Up" in c.get("State", "")
                            or c.get("State", "") == "running"
                        ]
                        if len(running) < 5:
                            need_rebuild = True
                    except json.JSONDecodeError:
                        # Docker compose ps text might be malformed on older versions
                        need_rebuild = True
            except Exception as e:
                logger.warning(f"Failed to check docker status, will rebuild: {e}")
                need_rebuild = True

        if need_rebuild:
            logger.info("Rebuilding / Restarting MCP Docker Mesh...")
            subprocess.run(
                ["docker", "compose"] + compose_args + ["down"],
                cwd=self.workspace_root,
                check=False,
            )
            subprocess.run(
                ["docker", "compose"] + compose_args + ["up", "-d"],
                cwd=self.workspace_root,
                check=True,
            )
            return False
        else:
            logger.info("Reusing existing MCP Docker Mesh...")
            # Still ensure they are started
            subprocess.run(
                ["docker", "compose"] + compose_args + ["up", "-d"],
                cwd=self.workspace_root,
                check=True,
                timeout=120,
            )
            return True

    def _wait_for_health_checks(self, timeout: int = 15):
        """Wait for required ports to be accepting connections."""
        import urllib.request
        from urllib.error import HTTPError, URLError

        logger.info("Running health-check handshakes to MCP ports...")
        start_time = time.time()

        pending_ports = set(self.required_ports)

        while pending_ports and (time.time() - start_time) < timeout:
            connected = []
            for port in pending_ports:
                try:
                    # In docker-proxy, TCP connect might succeed even if backend is starting,
                    # so we attempt a basic HTTP ping if applicable, or fallback to pure TCP.
                    req = urllib.request.Request(f"http://127.0.0.1:{port}/")
                    try:
                        urllib.request.urlopen(req, timeout=1.0)
                        connected.append(port)  # Got HTTP 200
                    except HTTPError:
                        # Any HTTP error (e.g. 404) means the server is UP!
                        connected.append(port)
                    except URLError:
                        # Connection refused or timeout
                        pass
                except Exception:
                    pass
            for p in connected:
                pending_ports.remove(p)

            if pending_ports:
                time.sleep(1.0)

        if pending_ports:
            raise RuntimeError(
                f"Failed health-check for MCP ports: {pending_ports} after {timeout} seconds."
            )

    def _check_sqlite_integrity(self):
        """Phase 2.1 checks DB integrity via PRAGMA if inherited container."""
        compose_args = self._get_compose_args()
        if not compose_args:
            return

        logger.info("Verifying inherited SQLite integrity...")
        dbs = [
            ("mcp-memory", "/data/memory.db"),
            ("mcp-agent-bus", "/data/agent_bus.db"),
        ]

        for service, path in dbs:
            try:
                cmd = (
                    ["docker", "compose"]
                    + compose_args
                    + [
                        "exec",
                        service,
                        "python",
                        "-c",
                        f"import sqlite3, sys; import os; sys.exit(0) if not os.path.exists('{path}') or sqlite3.connect('{path}').execute('PRAGMA integrity_check').fetchone()[0] == 'ok' else sys.exit(1)",  # noqa: E501
                    ]
                )
                subprocess.run(
                    cmd,
                    check=True,
                    cwd=self.workspace_root,
                    capture_output=True,
                    timeout=120,
                )
            except subprocess.CalledProcessError:
                logger.error(
                    f"Integrity check failed for {service} at {path}. Triggering forced rebuild."
                )
                self.force_rebuild_mcps = True
                self._ensure_containers()
                # Wait for health checks again after rebuilding
                self._wait_for_health_checks()
                break
            except Exception as e:
                logger.warning(f"Error checking integrity for {service}: {e}")

    def _hydrate_state(self):
        """Phase 2.2: Data Hydration from snapshot if DB is empty."""
        snapshot_dir = self.workspace_root / ".copilot/softwareFactoryVscode/.tmp" / "factory_snapshots"
        if not snapshot_dir.exists():
            return

        compose_args = self._get_compose_args()
        if not compose_args:
            return

        dbs = [
            ("mcp-memory", "/data/memory.db", snapshot_dir / "memory.db"),
            ("mcp-agent-bus", "/data/agent_bus.db", snapshot_dir / "agent_bus.db"),
        ]

        for service, dest_path, snap_path in dbs:
            if not snap_path.exists() or snap_path.stat().st_size == 0:
                continue

            # Check if active DB is empty (0 tables)
            try:
                cmd_check_empty = (
                    ["docker", "compose"]
                    + compose_args
                    + [
                        "exec",
                        service,
                        "python",
                        "-c",
                        f"import sqlite3, sys, os; sys.exit(0) if not os.path.exists('{dest_path}') or os.path.getsize('{dest_path}') < 8192 or sqlite3.connect('{dest_path}').execute(\"SELECT COUNT(*) FROM sqlite_master WHERE type='table'\").fetchone()[0] == 0 else sys.exit(1)",  # noqa: E501
                    ]
                )
                res = subprocess.run(
                    cmd_check_empty,
                    cwd=self.workspace_root,
                    capture_output=True,
                )

                # If exit code is 0, it is empty and we should hydrate
                if res.returncode == 0:
                    logger.info(f"Hydrating {service} from {snap_path}...")

                    tmp_bak = f"/tmp/{snap_path.name}.bak"
                    # copy snapshot inside container
                    subprocess.run(
                        ["docker", "compose"]
                        + compose_args
                        + ["cp", str(snap_path), f"{service}:{tmp_bak}"],
                        cwd=self.workspace_root,
                        check=True,
                        timeout=120,
                    )
                    # restore
                    restore_cmd = (
                        ["docker", "compose"]
                        + compose_args
                        + [
                            "exec",
                            service,
                            "python",
                            "-c",
                            f"import sqlite3; source=sqlite3.connect('{tmp_bak}'); dest=sqlite3.connect('{dest_path}'); source.backup(dest); source.close(); dest.close()",  # noqa: E501
                        ]
                    )
                    subprocess.run(
                        restore_cmd, cwd=self.workspace_root, check=True, timeout=120
                    )
            except Exception as e:
                logger.warning(f"Hydration failed for {service}: {e}")

    def teardown(self):
        """Phase 3.3: Orphan Sweeping (Teardown hooks)"""
        if getattr(self, "_teardown_handled", False):
            return
        self._teardown_handled = True

        # Snapshotting will go here (Ticket 3)
        self._take_snapshots()

        if self.kill_mcps_on_exit:
            logger.info("Sweeping orphan MCP containers (--kill-mcps-on-exit is set).")
            self._stop_containers()
        else:
            logger.info("Skipping orphan sweep. Containers will remain running.")

    def _take_snapshots(self):
        """Phase 3.2: Snapshot Dump"""
        snapshot_dir = self.workspace_root / ".copilot/softwareFactoryVscode/.tmp" / "factory_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        compose_args = self._get_compose_args()
        if not compose_args:
            return

        logger.info("Taking snapshots of MCP memory and agent-bus...")

        # We know mcp-memory has /data/memory.db
        try:
            subprocess.run(
                ["docker", "compose"]
                + compose_args
                + [
                    "exec",
                    "mcp-memory",
                    "python",
                    "-c",
                    "import sqlite3; con=sqlite3.connect('/data/memory.db'); bck=sqlite3.connect('/tmp/memory.db.bak'); con.backup(bck); bck.close(); con.close()",  # noqa: E501
                ],
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                timeout=120,
            )
            subprocess.run(
                ["docker", "compose"]
                + compose_args
                + [
                    "cp",
                    "mcp-memory:/tmp/memory.db.bak",
                    str(snapshot_dir / "memory.db"),
                ],
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                timeout=120,
            )
        except Exception as e:
            logger.warning(f"Failed to snapshot mcp-memory: {e}")

        # We know mcp-agent-bus has /data/agent_bus.db
        try:
            subprocess.run(
                ["docker", "compose"]
                + compose_args
                + [
                    "exec",
                    "mcp-agent-bus",
                    "python",
                    "-c",
                    "import sqlite3; con=sqlite3.connect('/data/agent_bus.db'); bck=sqlite3.connect('/tmp/agent_bus.db.bak'); con.backup(bck); bck.close(); con.close()",  # noqa: E501
                ],
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                timeout=120,
            )
            subprocess.run(
                ["docker", "compose"]
                + compose_args
                + [
                    "cp",
                    "mcp-agent-bus:/tmp/agent_bus.db.bak",
                    str(snapshot_dir / "agent_bus.db"),
                ],
                cwd=self.workspace_root,
                check=True,
                capture_output=True,
                timeout=120,
            )
        except Exception as e:
            logger.warning(f"Failed to snapshot mcp-agent-bus: {e}")

    def _stop_containers(self):
        """Teardown the Docker compose services (stop and remove)."""
        compose_args = self._get_compose_args()
        if compose_args:
            try:
                cmd = ["docker", "compose"] + compose_args + ["down"]
                subprocess.run(
                    cmd,
                    check=True,
                    cwd=self.workspace_root,
                    capture_output=True,
                    timeout=120,
                )
            except Exception as e:
                logger.error(f"Failed to tear down containers: {e}")
