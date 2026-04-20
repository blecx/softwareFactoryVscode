"""Authoritative MCP runtime-manager contract.

This phase-1 implementation establishes one dedicated runtime-truth surface
outside the harness layer, as sequenced by
`docs/architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md` and governed by
`ADR-013`, `ADR-014`, `ADR-009`, and `ADR-012`.
"""

from __future__ import annotations

import importlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import factory_workspace

from factory_runtime.mcp_runtime.catalog import build_catalog
from factory_runtime.mcp_runtime.models import (
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RecommendedAction,
    RepairResult,
    RepairStep,
    RuntimeCatalog,
    RuntimeLifecycleState,
    RuntimeProfileName,
    RuntimeSnapshot,
    SelectionMetadata,
    ServiceCatalogEntry,
    ServiceInstanceStatus,
    ServiceRuntimeRecord,
)

_PORT_MAPPING_PATTERN = re.compile(r"(?P<host>\d+)->(?P<container>\d+)/(?:tcp|udp)")


class MCPRuntimeManager:
    """Single authoritative contract for MCP runtime truth.

    The manager owns service-catalog loading, snapshot assembly, normalized
    reason-code evaluation, and lifecycle/repair entrypoints. `installed` and
    `active` remain separate selection facts rather than lifecycle-state aliases.
    """

    def __init__(
        self,
        *,
        registry_path: Path | None = None,
        default_workspace_file: str = factory_workspace.DEFAULT_WORKSPACE_FILENAME,
        docker_available_checker: Callable[[], bool] | None = None,
        service_inventory_loader: (
            Callable[[str], dict[str, dict[str, Any]]] | None
        ) = None,
    ) -> None:
        self._registry_path = registry_path
        self._default_workspace_file = default_workspace_file
        self._docker_available_checker = docker_available_checker
        self._service_inventory_loader = service_inventory_loader

    def load_catalog(self) -> RuntimeCatalog:
        return build_catalog()

    def resolve_env_file(self, repo_root: Path, env_file: Path | None = None) -> Path:
        if env_file is not None:
            return env_file.expanduser().resolve()

        candidates = [(repo_root / ".factory.env").resolve()]
        if len(repo_root.parents) > 1:
            companion_env = (
                repo_root.parents[1]
                / factory_workspace.FACTORY_DIRNAME
                / ".factory.env"
            ).resolve()
            if companion_env not in candidates:
                candidates.append(companion_env)

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return candidates[0]

    def build_snapshot(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        workspace_file: str | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> RuntimeSnapshot:
        catalog = self.load_catalog()
        profile_selection = catalog.select_profiles(selected_profiles)
        resolved_workspace_file = workspace_file or self._default_workspace_file
        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        target_dir = self._resolve_target_dir_from_env(repo_root, resolved_env_file)
        config = factory_workspace.build_runtime_config(
            target_dir,
            factory_dir=repo_root,
            workspace_file=resolved_workspace_file,
            registry_path=self._registry_path,
        )
        manifest, _ = factory_workspace.load_or_rebuild_runtime_manifest(
            target_dir,
            registry_path=self._registry_path,
        )
        if not manifest:
            manifest = factory_workspace.load_json(config.runtime_manifest_path)

        registry = factory_workspace.load_registry(self._registry_path)
        raw_record = registry.get("workspaces", {}).get(config.factory_instance_id, {})
        record = raw_record if isinstance(raw_record, dict) else {}
        installed = factory_workspace.has_managed_workspace_contract(target_dir)
        selection = SelectionMetadata(
            installed=installed,
            active=registry.get("active_workspace", "") == config.factory_instance_id,
            profiles=profile_selection,
        )

        runtime_topology = manifest.get("runtime_topology")
        if not isinstance(runtime_topology, dict):
            runtime_topology = factory_workspace.build_runtime_topology(config)
        shared_mode_diagnostics = factory_workspace.build_shared_mode_diagnostics(
            config
        )
        workspace_urls = self._load_workspace_server_urls(config.workspace_file_path)
        manifest_server_urls = self._load_manifest_server_urls(manifest)
        manifest_health_urls = self._load_manifest_health_urls(manifest)
        expected_workspace_urls = dict(config.mcp_server_urls)
        expected_health_urls = factory_workspace.build_runtime_health_urls_for_topology(
            config
        )
        expected_service_ports = self._build_expected_service_ports(
            config,
            catalog,
            profile_selection.required_services,
        )

        docker_available = self._docker_available()
        inventory_error: str | None = None
        service_inventory: dict[str, dict[str, Any]] = {}
        if docker_available:
            try:
                service_inventory = self._collect_service_inventory(
                    config.compose_project_name
                )
            except subprocess.CalledProcessError as exc:
                inventory_error = str(exc)
                service_inventory = {}

        services = self._build_service_records(
            config,
            catalog,
            profile_selection.required_services,
            runtime_topology,
            service_inventory,
            expected_workspace_urls,
            expected_health_urls,
            expected_service_ports,
        )
        lifecycle_state = self._infer_lifecycle_state(
            persisted_runtime_state=str(
                record.get("runtime_state", "installed")
            ).strip()
            or "installed",
            services=services,
            docker_available=docker_available,
            installed=installed,
        )
        last_transition_reason_codes = self._tuple_unique(
            [ReasonCode.REGISTRY_RECORD_MISSING] if not record and installed else []
        )

        snapshot = RuntimeSnapshot(
            workspace_id=config.project_workspace_id,
            instance_id=config.factory_instance_id,
            target_dir=config.target_dir,
            factory_dir=config.factory_dir,
            compose_project_name=config.compose_project_name,
            lifecycle_state=lifecycle_state,
            selection=selection,
            persisted_runtime_state=str(
                record.get("runtime_state", "installed")
            ).strip()
            or "installed",
            last_transition_at=str(
                record.get("updated_at") or record.get("installed_at") or ""
            ).strip()
            or None,
            last_transition_reason_codes=last_transition_reason_codes,
            shared_mode=config.shared_service_mode,
            shared_mode_status=str(
                shared_mode_diagnostics.get("shared_mode_status", "")
            ),
            runtime_topology=runtime_topology,
            shared_mode_diagnostics=shared_mode_diagnostics,
            workspace_urls=workspace_urls,
            manifest_server_urls=manifest_server_urls,
            manifest_health_urls=manifest_health_urls,
            expected_workspace_urls=expected_workspace_urls,
            expected_health_urls=expected_health_urls,
            expected_service_ports=expected_service_ports,
            services=services,
            catalog=catalog,
            docker_available=docker_available,
            inventory_error=inventory_error,
        )
        readiness = self.evaluate_readiness(snapshot)
        return replace(
            snapshot,
            readiness=readiness,
            last_transition_reason_codes=self._tuple_unique(
                [*snapshot.last_transition_reason_codes, *readiness.reason_codes]
            ),
        )

    def evaluate_readiness(self, snapshot: RuntimeSnapshot) -> ReadinessResult:
        config_drift_issues: list[str] = []
        config_drift_codes: list[ReasonCode] = []
        blocking_services: list[str] = []
        service_issues: list[str] = []
        service_codes: list[ReasonCode] = []
        running_service_count = 0

        if not snapshot.selection.installed:
            return ReadinessResult(
                status=ReadinessStatus.ERROR,
                recommended_action=RecommendedAction.INSPECT_REGISTRY,
                ready=False,
                reason_codes=(ReasonCode.MISSING_RUNTIME_METADATA,),
                issues=(
                    "Runtime metadata required for snapshot assembly is missing for "
                    f"workspace `{snapshot.workspace_id}`.",
                ),
            )

        if not snapshot.docker_available:
            return ReadinessResult(
                status=ReadinessStatus.DOCKER_UNAVAILABLE,
                recommended_action=RecommendedAction.INSTALL_DOCKER,
                ready=False,
                reason_codes=(ReasonCode.DOCKER_UNAVAILABLE,),
                issues=("Docker CLI is not available on PATH.",),
            )

        if snapshot.inventory_error:
            return ReadinessResult(
                status=ReadinessStatus.DOCKER_ERROR,
                recommended_action=RecommendedAction.INSPECT_DOCKER,
                ready=False,
                reason_codes=(ReasonCode.DOCKER_INSPECTION_FAILED,),
                issues=(
                    "Unable to inspect Docker runtime state for compose project "
                    f"`{snapshot.compose_project_name}`: {snapshot.inventory_error}",
                ),
            )

        topology_issues = factory_workspace.validate_runtime_topology(
            self._build_runtime_config_from_snapshot(snapshot)
        )
        if topology_issues:
            config_drift_issues.extend(topology_issues)
            config_drift_codes.extend(
                [ReasonCode.SHARED_SERVICE_DISCOVERY_MISSING] * len(topology_issues)
            )

        shared_mode_issues = factory_workspace.build_shared_mode_diagnostic_issues(
            self._build_runtime_config_from_snapshot(snapshot)
        )
        if shared_mode_issues:
            config_drift_issues.extend(shared_mode_issues)
            config_drift_codes.extend(
                [ReasonCode.SHARED_MODE_TENANT_ENFORCEMENT_MISSING]
                * len(shared_mode_issues)
            )

        catalog = snapshot.catalog or self.load_catalog()
        profile_services = snapshot.selection.profiles.required_services

        for service_name in profile_services:
            entry = catalog.services[service_name]
            if entry.workspace_server_name:
                expected_url = snapshot.expected_workspace_urls.get(
                    entry.workspace_server_name, ""
                )
                workspace_url = snapshot.workspace_urls.get(
                    entry.workspace_server_name, ""
                )
                if workspace_url != expected_url:
                    config_drift_issues.append(
                        "Generated workspace MCP URL drift detected for "
                        f"`{entry.workspace_server_name}` (expected `{expected_url}`, "
                        f"found `{workspace_url or 'missing'}`)."
                    )
                    config_drift_codes.append(ReasonCode.WORKSPACE_URL_DRIFT)

                manifest_url = snapshot.manifest_server_urls.get(
                    entry.workspace_server_name,
                    "",
                )
                if manifest_url != expected_url:
                    config_drift_issues.append(
                        "Runtime manifest MCP URL drift detected for "
                        f"`{entry.workspace_server_name}` (expected `{expected_url}`, "
                        f"found `{manifest_url or 'missing'}`)."
                    )
                    config_drift_codes.append(ReasonCode.MANIFEST_SERVER_URL_DRIFT)

            expected_health_url = snapshot.expected_health_urls.get(service_name, "")
            if expected_health_url:
                manifest_health_url = snapshot.manifest_health_urls.get(
                    service_name, ""
                )
                if manifest_health_url != expected_health_url:
                    config_drift_issues.append(
                        "Runtime manifest health URL drift detected for "
                        f"`{service_name}` (expected `{expected_health_url}`, found "
                        f"`{manifest_health_url or 'missing'}`)."
                    )
                    config_drift_codes.append(ReasonCode.MANIFEST_HEALTH_URL_DRIFT)

            service_record = snapshot.services[service_name]
            if service_record.status == ServiceInstanceStatus.RUNNING:
                running_service_count += 1
                continue
            if service_record.status == ServiceInstanceStatus.EXTERNAL:
                continue
            config_drift_reason_codes = [
                reason_code
                for reason_code in service_record.reason_codes
                if reason_code
                in {
                    ReasonCode.SHARED_MODE_WORKSPACE_DUPLICATE,
                    ReasonCode.SERVICE_PORT_MISMATCH,
                }
            ]
            service_reason_codes = [
                reason_code
                for reason_code in service_record.reason_codes
                if reason_code not in config_drift_reason_codes
            ]

            if config_drift_reason_codes:
                blocking_services.append(service_name)
                config_drift_codes.extend(config_drift_reason_codes)
                if service_record.details:
                    config_drift_issues.extend(service_record.details)

            if service_reason_codes:
                blocking_services.append(service_name)
                service_codes.extend(service_reason_codes)
                if service_record.details:
                    service_issues.extend(service_record.details)
            elif service_record.details and not config_drift_reason_codes:
                service_issues.extend(service_record.details)

        config_issue_codes = set(config_drift_codes)
        shared_only_issue_codes = {
            ReasonCode.SHARED_SERVICE_DISCOVERY_MISSING,
            ReasonCode.SHARED_MODE_TENANT_ENFORCEMENT_MISSING,
            ReasonCode.SHARED_MODE_WORKSPACE_DUPLICATE,
        }
        has_alignment_or_port_drift = (
            bool(
                config_issue_codes
                - {
                    *shared_only_issue_codes,
                }
            )
            or ReasonCode.SERVICE_PORT_MISMATCH in service_codes
        )

        if config_drift_issues:
            recommended_action = (
                RecommendedAction.INSPECT_SHARED_TOPOLOGY
                if not has_alignment_or_port_drift
                else RecommendedAction.REBOOTSTRAP
            )
            return ReadinessResult(
                status=ReadinessStatus.CONFIG_DRIFT,
                recommended_action=recommended_action,
                ready=False,
                reason_codes=self._tuple_unique(config_drift_codes),
                issues=tuple(config_drift_issues),
                blocking_services=tuple(dict.fromkeys(blocking_services)),
            )

        if running_service_count == 0:
            return ReadinessResult(
                status=ReadinessStatus.NEEDS_RAMP_UP,
                recommended_action=RecommendedAction.START,
                ready=False,
                reason_codes=(ReasonCode.NO_RUNNING_SERVICES,),
                issues=(
                    "Runtime preflight detected no running containers for compose "
                    f"project `{snapshot.compose_project_name}`. Infrastructure needs "
                    "ramp-up via `factory_stack.py start`.",
                ),
            )

        if service_issues:
            return ReadinessResult(
                status=ReadinessStatus.DEGRADED,
                recommended_action=RecommendedAction.INSPECT,
                ready=False,
                reason_codes=self._tuple_unique(service_codes),
                issues=tuple(service_issues),
                blocking_services=tuple(dict.fromkeys(blocking_services)),
            )

        return ReadinessResult(
            status=ReadinessStatus.READY,
            recommended_action=RecommendedAction.NONE,
            ready=True,
        )

    def start(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        build: bool = True,
        wait: bool = True,
        wait_timeout: int = 300,
        foreground: bool = False,
    ) -> Path:
        stack = self._load_factory_stack_module()
        return stack.start_stack(
            repo_root,
            env_file=env_file,
            build=build,
            wait=wait,
            wait_timeout=wait_timeout,
            foreground=foreground,
        )

    def stop(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        remove_volumes: bool = False,
        preserve_runtime_state: bool = False,
    ) -> Path:
        stack = self._load_factory_stack_module()
        return stack.stop_stack(
            repo_root,
            env_file=env_file,
            remove_volumes=remove_volumes,
            preserve_runtime_state=preserve_runtime_state,
        )

    def cleanup(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        trigger: str = "cleanup",
    ) -> int:
        del trigger
        stack = self._load_factory_stack_module()
        return int(stack.cleanup_workspace(repo_root, env_file=env_file))

    def repair(
        self,
        repo_root: Path | None = None,
        *,
        env_file: Path | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> RepairResult:
        del env_file, selected_profiles
        final_state = None
        if repo_root is not None:
            try:
                snapshot = self.build_snapshot(repo_root)
            except Exception:
                final_state = None
            else:
                final_state = snapshot.lifecycle_state
        return RepairResult(
            attempted=False,
            success=False,
            attempted_steps=(RepairStep.REPROBE,),
            reason_codes=(ReasonCode.REPAIR_NOT_IMPLEMENTED,),
            details=(
                "Phase 1 establishes the repair contract surface only; bounded "
                "repair semantics land in the later cleanup/repair rollout slice.",
            ),
            final_state=final_state,
        )

    def _resolve_target_dir_from_env(self, repo_root: Path, env_file: Path) -> Path:
        env_values = factory_workspace.parse_env_file(env_file)
        target_value = env_values.get("TARGET_WORKSPACE_PATH", "").strip()
        if target_value:
            return Path(target_value).expanduser().resolve()
        if len(repo_root.parents) > 1:
            return repo_root.parents[1].resolve()
        return repo_root.resolve()

    def _docker_available(self) -> bool:
        if self._docker_available_checker is not None:
            return bool(self._docker_available_checker())
        return shutil.which("docker") is not None

    def _collect_service_inventory(
        self,
        compose_project_name: str,
    ) -> dict[str, dict[str, Any]]:
        if self._service_inventory_loader is not None:
            return self._service_inventory_loader(compose_project_name)

        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"label=com.docker.compose.project={compose_project_name}",
                "--format",
                '{{.Label "com.docker.compose.service"}}|{{.Status}}|{{.Image}}|{{.Ports}}',
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        inventory: dict[str, dict[str, Any]] = {}
        for line in result.stdout.splitlines():
            if not line.strip() or "|" not in line:
                continue
            service, status, image, ports_text = (
                line.split("|", 3) + ["", "", "", ""]
            )[:4]
            inventory[service.strip()] = {
                "status": status.strip(),
                "image": image.strip(),
                "ports_text": ports_text.strip(),
                "published_ports": tuple(
                    self._parse_published_ports(ports_text.strip())
                ),
            }
        return inventory

    def _parse_published_ports(self, ports_text: str) -> list[int]:
        return sorted(
            {
                int(match.group("host"))
                for match in _PORT_MAPPING_PATTERN.finditer(ports_text)
            }
        )

    def _load_workspace_server_urls(self, workspace_path: Path) -> dict[str, str]:
        if not workspace_path.exists():
            return {}
        try:
            config_data = json.loads(workspace_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        servers = config_data.get("settings", {}).get("mcp", {}).get("servers", {})
        if not isinstance(servers, dict):
            return {}
        urls: dict[str, str] = {}
        for name, data in servers.items():
            if isinstance(data, dict) and isinstance(data.get("url"), str):
                urls[name] = str(data["url"])
        return urls

    def _load_manifest_server_urls(self, manifest: dict[str, Any]) -> dict[str, str]:
        return {
            name: str(data.get("url", ""))
            for name, data in manifest.get("mcp_servers", {}).items()
            if isinstance(data, dict)
        }

    def _load_manifest_health_urls(self, manifest: dict[str, Any]) -> dict[str, str]:
        return {
            name: str(data.get("url", ""))
            for name, data in manifest.get("runtime_health", {}).items()
            if isinstance(data, dict)
        }

    def _build_expected_service_ports(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        catalog: RuntimeCatalog,
        required_services: Sequence[str],
    ) -> dict[str, int]:
        workspace_owned_runtime_services = (
            factory_workspace.workspace_owned_runtime_services(config)
        )
        expected_ports: dict[str, int] = {}
        for service_name in required_services:
            entry = catalog.services[service_name]
            if not entry.port_env_key:
                continue
            if (
                service_name in factory_workspace.RUNTIME_SERVICE_CONTRACT
                and service_name not in workspace_owned_runtime_services
            ):
                continue
            expected_ports[service_name] = config.ports[entry.port_env_key]
        return expected_ports

    def _build_service_records(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        catalog: RuntimeCatalog,
        required_services: Sequence[str],
        runtime_topology: dict[str, Any],
        service_inventory: dict[str, dict[str, Any]],
        expected_workspace_urls: dict[str, str],
        expected_health_urls: dict[str, str],
        expected_service_ports: dict[str, int],
    ) -> dict[str, ServiceRuntimeRecord]:
        records: dict[str, ServiceRuntimeRecord] = {}
        topology_services = runtime_topology.get("services", {})
        topology_services = (
            topology_services if isinstance(topology_services, dict) else {}
        )

        for service_name in required_services:
            entry = catalog.services[service_name]
            topology_entry = topology_services.get(service_name, {})
            topology_entry = topology_entry if isinstance(topology_entry, dict) else {}
            workspace_owned = bool(
                topology_entry.get("workspace_owned")
                if topology_entry
                else service_name not in factory_workspace.PROMOTABLE_SHARED_SERVICES
            )
            topology_mode = str(
                topology_entry.get(
                    "topology_mode",
                    factory_workspace.PER_WORKSPACE_TOPOLOGY_MODE,
                )
            )
            discovery_url = str(topology_entry.get("discovery_url", ""))
            if not discovery_url and entry.workspace_server_name:
                discovery_url = expected_workspace_urls.get(
                    entry.workspace_server_name, ""
                )
            probe_url = str(topology_entry.get("probe_url", ""))
            if not probe_url:
                probe_url = expected_health_urls.get(service_name, discovery_url)

            service_entry = service_inventory.get(service_name)
            docker_status = ""
            published_ports: tuple[int, ...] = ()
            expected_port = expected_service_ports.get(service_name)
            reason_codes: list[ReasonCode] = []
            details: list[str] = []

            if service_entry:
                docker_status = str(service_entry.get("status", ""))
                published_ports = tuple(
                    int(port) for port in service_entry.get("published_ports", ())
                )
                lowered = docker_status.lower()
                if not workspace_owned:
                    status = ServiceInstanceStatus.DEGRADED
                    reason_codes.append(ReasonCode.SHARED_MODE_WORKSPACE_DUPLICATE)
                    details.append(
                        "Shared-service topology drift detected: promoted shared "
                        f"service `{service_name}` is still instantiated inside "
                        f"workspace compose project `{config.compose_project_name}`."
                    )
                elif "up" not in lowered:
                    status = ServiceInstanceStatus.DEGRADED
                    reason_codes.append(ReasonCode.SERVICE_NOT_RUNNING)
                    details.append(
                        "Runtime service "
                        f"`{service_name}` is not currently running (docker status: "
                        f"`{docker_status}`)."
                    )
                elif (
                    entry.readiness.requires_container_healthy
                    and "healthy" not in lowered
                ):
                    status = ServiceInstanceStatus.DEGRADED
                    reason_codes.append(ReasonCode.SERVICE_UNHEALTHY)
                    details.append(
                        "Runtime service "
                        f"`{service_name}` is running without a healthy status "
                        f"(docker status: `{docker_status}`)."
                    )
                elif expected_port is not None and expected_port not in published_ports:
                    status = ServiceInstanceStatus.DEGRADED
                    reason_codes.append(ReasonCode.SERVICE_PORT_MISMATCH)
                    details.append(
                        "Runtime service "
                        f"`{service_name}` is not published on expected host port "
                        f"`{expected_port}` (found `{list(published_ports) or 'none'}`)."
                    )
                else:
                    status = ServiceInstanceStatus.RUNNING
            elif not workspace_owned:
                status = ServiceInstanceStatus.EXTERNAL
            else:
                status = ServiceInstanceStatus.MISSING
                reason_codes.append(ReasonCode.SERVICE_MISSING)
                details.append(
                    "Expected runtime service is missing for compose project "
                    f"`{config.compose_project_name}`: `{service_name}`."
                )

            records[service_name] = ServiceRuntimeRecord(
                service_name=service_name,
                runtime_identity=entry.runtime_identity,
                service_kind=entry.service_kind,
                scope=entry.scope,
                topology_mode=topology_mode,
                workspace_owned=workspace_owned,
                status=status,
                docker_status=docker_status,
                published_ports=published_ports,
                expected_port=expected_port,
                workspace_server_name=entry.workspace_server_name,
                discovery_url=discovery_url,
                probe_url=probe_url,
                reason_codes=self._tuple_unique(reason_codes),
                details=tuple(details),
            )

        return records

    def _infer_lifecycle_state(
        self,
        *,
        persisted_runtime_state: str,
        services: dict[str, ServiceRuntimeRecord],
        docker_available: bool,
        installed: bool,
    ) -> RuntimeLifecycleState:
        if not installed:
            return RuntimeLifecycleState.RUNTIME_DELETED
        if persisted_runtime_state == "starting":
            return RuntimeLifecycleState.STARTING
        if persisted_runtime_state in {"failed", "degraded"}:
            return RuntimeLifecycleState.DEGRADED
        if not docker_available:
            return (
                RuntimeLifecycleState.RUNNING
                if persisted_runtime_state == "running"
                else RuntimeLifecycleState.STOPPED
            )
        if not services:
            return RuntimeLifecycleState.STOPPED

        non_external = [
            record
            for record in services.values()
            if record.status != ServiceInstanceStatus.EXTERNAL
        ]
        if not non_external:
            return RuntimeLifecycleState.RUNNING
        if all(
            record.status == ServiceInstanceStatus.MISSING for record in non_external
        ):
            return RuntimeLifecycleState.STOPPED
        if any(
            record.status
            in {ServiceInstanceStatus.DEGRADED, ServiceInstanceStatus.MISSING}
            for record in non_external
        ):
            return RuntimeLifecycleState.DEGRADED
        if any(
            record.status == ServiceInstanceStatus.RUNNING for record in non_external
        ):
            return RuntimeLifecycleState.RUNNING
        return RuntimeLifecycleState.STOPPED

    def _build_runtime_config_from_snapshot(
        self,
        snapshot: RuntimeSnapshot,
    ) -> factory_workspace.WorkspaceRuntimeConfig:
        return factory_workspace.build_runtime_config(
            snapshot.target_dir,
            factory_dir=snapshot.factory_dir,
            workspace_file=self._default_workspace_file,
            registry_path=self._registry_path,
        )

    def _load_factory_stack_module(self) -> Any:
        return importlib.import_module("factory_stack")

    def _tuple_unique(
        self,
        values: Iterable[ReasonCode],
    ) -> tuple[ReasonCode, ...]:
        return tuple(dict.fromkeys(values))
