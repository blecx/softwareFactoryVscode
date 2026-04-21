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
import time
from dataclasses import replace
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import factory_workspace

from factory_runtime.mcp_runtime.catalog import build_catalog
from factory_runtime.mcp_runtime.models import (
    LeaseKind,
    LeaseMetadata,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RecommendedAction,
    RecoveryClassification,
    RecoveryMetadata,
    RepairResult,
    RepairStep,
    RuntimeActionTrigger,
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
_METADATA_DRIFT_REASON_CODES = {
    ReasonCode.WORKSPACE_URL_DRIFT,
    ReasonCode.MANIFEST_SERVER_URL_DRIFT,
    ReasonCode.MANIFEST_HEALTH_URL_DRIFT,
    ReasonCode.SHARED_SERVICE_DISCOVERY_MISSING,
    ReasonCode.SHARED_MODE_TENANT_ENFORCEMENT_MISSING,
    ReasonCode.SHARED_MODE_WORKSPACE_DUPLICATE,
    ReasonCode.REGISTRY_RECORD_MISSING,
    ReasonCode.MISSING_RUNTIME_METADATA,
}
_RESTART_REASON_CODES = {
    ReasonCode.NO_RUNNING_SERVICES,
    ReasonCode.SERVICE_NOT_RUNNING,
    ReasonCode.SERVICE_UNHEALTHY,
}
_RECREATE_REASON_CODES = {
    ReasonCode.SERVICE_MISSING,
    ReasonCode.SERVICE_PORT_MISMATCH,
    ReasonCode.ENDPOINT_UNREACHABLE,
    ReasonCode.MCP_INITIALIZE_FAILED,
}
_SECRET_KEY_TOKENS = (
    "secret",
    "token",
    "password",
    "api_key",
    "apikey",
    "key",
)
DEFAULT_RUNTIME_PROBE_TIMEOUT = 2.0
DEFAULT_MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_SESSION_ID_HEADER = "mcp-session-id"
MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
MCP_ACCEPT_HEADER = "application/json, text/event-stream"


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
        stack_module_loader: Callable[[], Any] | None = None,
        http_probe_func: Callable[[str, float, bool], str | None] | None = None,
        mcp_initialize_probe: Callable[[str, float, str], str | None] | None = None,
        readiness_probe_timeout: float = DEFAULT_RUNTIME_PROBE_TIMEOUT,
        repair_backoff_seconds: Sequence[float] = (0.0,),
        sleep_func: Callable[[float], None] | None = None,
        max_repair_failures: int = 3,
    ) -> None:
        self._registry_path = registry_path
        self._default_workspace_file = default_workspace_file
        self._docker_available_checker = docker_available_checker
        self._service_inventory_loader = service_inventory_loader
        self._stack_module_loader = stack_module_loader
        self._http_probe_func = http_probe_func
        self._mcp_initialize_probe = mcp_initialize_probe
        self._readiness_probe_timeout = max(0.1, float(readiness_probe_timeout))
        self._repair_backoff_seconds = tuple(repair_backoff_seconds) or (0.0,)
        self._sleep_func = sleep_func or time.sleep
        self._max_repair_failures = max(1, int(max_repair_failures))

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

    def candidate_runtime_manifest_paths(self, workspace_root: Path) -> list[Path]:
        resolved_root = workspace_root.resolve()
        candidates = [
            (
                resolved_root
                / factory_workspace.TMP_SUBPATH
                / factory_workspace.RUNTIME_MANIFEST_FILENAME
            ).resolve()
        ]
        if len(resolved_root.parents) > 1:
            companion_manifest = (
                resolved_root.parents[1]
                / factory_workspace.TMP_SUBPATH
                / factory_workspace.RUNTIME_MANIFEST_FILENAME
            ).resolve()
            if companion_manifest not in candidates:
                candidates.append(companion_manifest)
        return candidates

    def candidate_runtime_env_paths(self, workspace_root: Path) -> list[Path]:
        resolved_root = workspace_root.resolve()
        candidates = [
            (
                resolved_root / factory_workspace.FACTORY_DIRNAME / ".factory.env"
            ).resolve()
        ]
        if len(resolved_root.parents) > 1:
            companion_env = (
                resolved_root.parents[1]
                / factory_workspace.FACTORY_DIRNAME
                / ".factory.env"
            ).resolve()
            if companion_env not in candidates:
                candidates.append(companion_env)
        return candidates

    def resolve_factory_repo_root(self, workspace_root: Path) -> Path:
        target_factory = (workspace_root / factory_workspace.FACTORY_DIRNAME).resolve()
        if (target_factory / "scripts" / "factory_stack.py").exists():
            return target_factory

        source_factory = workspace_root.resolve()
        if (source_factory / "scripts" / "factory_stack.py").exists():
            return source_factory

        raise FileNotFoundError(
            "Unable to locate the canonical Software Factory repo from "
            f"workspace root `{workspace_root}`."
        )

    def resolve_workspace_env_file(
        self,
        workspace_root: Path,
        factory_repo_root: Path | None = None,
    ) -> Path:
        for candidate in self.candidate_runtime_env_paths(workspace_root):
            if candidate.exists():
                return candidate

        resolved_factory_repo_root = factory_repo_root
        if resolved_factory_repo_root is None:
            resolved_factory_repo_root = self.resolve_factory_repo_root(workspace_root)

        return self.resolve_env_file(resolved_factory_repo_root)

    def build_workspace_snapshot(
        self,
        workspace_root: Path,
        *,
        workspace_file: str | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> RuntimeSnapshot:
        factory_repo_root = self.resolve_factory_repo_root(workspace_root)
        env_file = self.resolve_workspace_env_file(
            workspace_root,
            factory_repo_root,
        )
        return self.build_snapshot(
            factory_repo_root,
            env_file=env_file,
            workspace_file=workspace_file,
            selected_profiles=selected_profiles,
        )

    def load_workspace_id(self, workspace_root: Path) -> str | None:
        try:
            snapshot = self.build_workspace_snapshot(
                workspace_root,
                selected_profiles=(RuntimeProfileName.HARNESS_DEFAULT,),
            )
        except Exception:  # noqa: BLE001
            snapshot = None

        if snapshot is not None and snapshot.workspace_id.strip():
            return snapshot.workspace_id

        for manifest_path in self.candidate_runtime_manifest_paths(workspace_root):
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            project_workspace_id = str(manifest.get("project_workspace_id", "")).strip()
            if project_workspace_id:
                return project_workspace_id

        for env_path in self.candidate_runtime_env_paths(workspace_root):
            values = factory_workspace.parse_env_file(env_path)
            project_workspace_id = values.get("PROJECT_WORKSPACE_ID", "").strip()
            if project_workspace_id:
                return project_workspace_id

        return None

    def load_named_urls_from_workspace(
        self,
        workspace_root: Path,
        mappings: dict[str, tuple[str, str]],
        *,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> dict[str, str]:
        try:
            snapshot = self.build_workspace_snapshot(
                workspace_root,
                selected_profiles=selected_profiles,
            )
        except Exception:  # noqa: BLE001
            snapshot = None
        else:
            snapshot_urls = self._extract_named_urls_from_snapshot(snapshot, mappings)
            if snapshot_urls:
                return snapshot_urls

        for manifest_path in self.candidate_runtime_manifest_paths(workspace_root):
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            manifest_urls = self._extract_named_urls_from_manifest(manifest, mappings)
            if manifest_urls:
                return manifest_urls

        return {}

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
        persisted_runtime_state = (
            self._coerce_optional_text(record.get("runtime_state")) or "installed"
        )
        active = registry.get("active_workspace", "") == config.factory_instance_id
        selection = self._build_selection_metadata(
            record,
            installed=installed,
            active=active,
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
            persisted_runtime_state=persisted_runtime_state,
            services=services,
            docker_available=docker_available,
            installed=installed,
        )
        last_transition_at = self._coerce_optional_text(
            record.get("updated_at") or record.get("installed_at")
        )
        last_transition_reason_codes = self._tuple_unique(
            [
                *self._extract_record_transition_reason_codes(
                    record,
                    persisted_runtime_state=persisted_runtime_state,
                    last_transition_at=last_transition_at,
                ),
                *(
                    [ReasonCode.REGISTRY_RECORD_MISSING]
                    if not record and installed
                    else []
                ),
            ]
        )

        snapshot = RuntimeSnapshot(
            workspace_id=config.project_workspace_id,
            instance_id=config.factory_instance_id,
            target_dir=config.target_dir,
            factory_dir=config.factory_dir,
            compose_project_name=config.compose_project_name,
            lifecycle_state=lifecycle_state,
            selection=selection,
            persisted_runtime_state=persisted_runtime_state,
            last_transition_at=last_transition_at,
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
        readiness = self.evaluate_readiness(snapshot, config=config)
        recovery = self._build_recovery_metadata(snapshot, record, readiness)
        return replace(
            snapshot,
            readiness=readiness,
            recovery=recovery,
            last_transition_reason_codes=self._tuple_unique(
                [*snapshot.last_transition_reason_codes, *readiness.reason_codes]
            ),
        )

    def evaluate_readiness(
        self,
        snapshot: RuntimeSnapshot,
        *,
        config: factory_workspace.WorkspaceRuntimeConfig | None = None,
    ) -> ReadinessResult:
        config_drift_issues: list[str] = []
        config_drift_codes: list[ReasonCode] = []
        blocking_services: list[str] = []
        service_issues: list[str] = []
        service_codes: list[ReasonCode] = []
        running_service_count = 0
        resolved_config = config
        if resolved_config is None:
            try:
                resolved_config = self._build_runtime_config_from_snapshot(snapshot)
            except Exception:  # noqa: BLE001
                resolved_config = None

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

        if resolved_config is not None:
            topology_issues = factory_workspace.validate_runtime_topology(
                resolved_config
            )
            if topology_issues:
                config_drift_issues.extend(topology_issues)
                config_drift_codes.extend(
                    [ReasonCode.SHARED_SERVICE_DISCOVERY_MISSING] * len(topology_issues)
                )

            shared_mode_issues = factory_workspace.build_shared_mode_diagnostic_issues(
                resolved_config
            )
            if shared_mode_issues:
                config_drift_issues.extend(shared_mode_issues)
                config_drift_codes.extend(
                    [ReasonCode.SHARED_MODE_TENANT_ENFORCEMENT_MISSING]
                    * len(shared_mode_issues)
                )

        catalog = snapshot.catalog or self.load_catalog()
        profile_services = snapshot.selection.profiles.required_services

        service_config_issues: dict[str, list[str]] = {}
        service_config_codes: dict[str, list[ReasonCode]] = {}
        service_runtime_issues: dict[str, list[str]] = {}
        service_runtime_codes: dict[str, list[ReasonCode]] = {}

        for service_name in profile_services:
            entry = catalog.services[service_name]
            config_issue_details = service_config_issues.setdefault(service_name, [])
            config_issue_codes = service_config_codes.setdefault(service_name, [])
            runtime_issue_details = service_runtime_issues.setdefault(service_name, [])
            runtime_issue_codes = service_runtime_codes.setdefault(service_name, [])
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
            if resolved_config is not None:
                missing_config_keys = self._missing_required_config_keys(
                    resolved_config,
                    entry,
                )
                for config_key in missing_config_keys:
                    reason_code = self._classify_required_config_reason(config_key)
                    config_issue_codes.append(reason_code)
                    config_issue_details.append(
                        "Runtime service "
                        f"`{service_name}` requires non-empty configuration key "
                        f"`{config_key}` before the runtime can be considered ready."
                    )

                if service_record.workspace_owned:
                    missing_mounts = self._missing_required_mount_paths(
                        resolved_config,
                        entry,
                    )
                    for mount_spec, resolved_mount_path in missing_mounts:
                        config_issue_codes.append(ReasonCode.MISSING_MOUNT)
                        config_issue_details.append(
                            "Runtime service "
                            f"`{service_name}` requires mount/resource path "
                            f"`{resolved_mount_path}` derived from `{mount_spec}`, "
                            "but it is missing."
                        )

            if service_record.status == ServiceInstanceStatus.RUNNING:
                running_service_count += 1
            elif service_record.status != ServiceInstanceStatus.EXTERNAL:
                current_config_drift_reason_codes = [
                    reason_code
                    for reason_code in service_record.reason_codes
                    if reason_code
                    in {
                        ReasonCode.SHARED_MODE_WORKSPACE_DUPLICATE,
                        ReasonCode.SERVICE_PORT_MISMATCH,
                    }
                ]
                current_service_reason_codes = [
                    reason_code
                    for reason_code in service_record.reason_codes
                    if reason_code not in current_config_drift_reason_codes
                ]

                config_issue_codes.extend(current_config_drift_reason_codes)
                if current_config_drift_reason_codes and service_record.details:
                    config_issue_details.extend(service_record.details)

                runtime_issue_codes.extend(current_service_reason_codes)
                if current_service_reason_codes and service_record.details:
                    runtime_issue_details.extend(service_record.details)
                elif service_record.details and not current_config_drift_reason_codes:
                    runtime_issue_details.extend(service_record.details)

            if (
                service_record.status
                in {
                    ServiceInstanceStatus.RUNNING,
                    ServiceInstanceStatus.EXTERNAL,
                }
                and entry.readiness.requires_endpoint_reachability
                and service_record.probe_url
            ):
                endpoint_error = self._probe_http_url(
                    service_record.probe_url,
                    allow_http_error=entry.readiness.allow_http_error,
                )
                if endpoint_error:
                    runtime_issue_codes.append(ReasonCode.ENDPOINT_UNREACHABLE)
                    runtime_issue_details.append(
                        "Runtime endpoint probe failed for service "
                        f"`{service_name}` at {service_record.probe_url}: "
                        f"{endpoint_error}"
                    )

            if (
                service_record.status
                in {ServiceInstanceStatus.RUNNING, ServiceInstanceStatus.EXTERNAL}
                and entry.readiness.requires_mcp_initialize
                and service_record.probe_url
            ):
                mcp_initialize_error = self._probe_mcp_initialize(
                    service_record.probe_url,
                    workspace_id=snapshot.workspace_id,
                )
                if mcp_initialize_error:
                    runtime_issue_codes.append(ReasonCode.MCP_INITIALIZE_FAILED)
                    runtime_issue_details.append(
                        "MCP initialize handshake failed for service "
                        f"`{service_name}` at {service_record.probe_url}: "
                        f"{mcp_initialize_error}"
                    )

        for service_name in profile_services:
            entry = catalog.services[service_name]
            if not entry.dependencies:
                continue

            dependency_failures: list[str] = []
            for dependency_name in entry.dependencies:
                dependency_record = snapshot.services.get(dependency_name)
                if dependency_record is None:
                    dependency_failures.append(
                        "Runtime dependency metadata is missing for dependent service "
                        f"`{dependency_name}` required by `{service_name}`."
                    )
                    continue

                dependency_has_blocker = bool(
                    service_config_issues.get(dependency_name)
                    or service_runtime_issues.get(dependency_name)
                )
                if (
                    dependency_record.status
                    not in {
                        ServiceInstanceStatus.RUNNING,
                        ServiceInstanceStatus.EXTERNAL,
                    }
                    or dependency_has_blocker
                ):
                    dependency_failures.append(
                        "Runtime dependency "
                        f"`{dependency_name}` is not healthy enough for dependent "
                        f"service `{service_name}` (status=`{dependency_record.status.value}`)."
                    )

            if dependency_failures:
                service_runtime_codes.setdefault(service_name, []).append(
                    ReasonCode.DEPENDENCY_UNHEALTHY
                )
                service_runtime_issues.setdefault(service_name, []).extend(
                    dependency_failures
                )

        for service_name in profile_services:
            current_config_issues = service_config_issues.get(service_name, [])
            current_runtime_issues = service_runtime_issues.get(service_name, [])
            if current_config_issues or current_runtime_issues:
                blocking_services.append(service_name)
            if current_config_issues:
                config_drift_issues.extend(current_config_issues)
                config_drift_codes.extend(service_config_codes.get(service_name, []))
            if current_runtime_issues:
                service_issues.extend(current_runtime_issues)
                service_codes.extend(service_runtime_codes.get(service_name, []))

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
        trigger: RuntimeActionTrigger | str = "cleanup",
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> int:
        stack = self._load_factory_stack_module()
        normalized_trigger = self._normalize_runtime_action_trigger(trigger)
        normalized_reason_codes = self._coerce_reason_codes(reason_codes)
        resolved_env_file = stack.resolve_env_file(repo_root, env_file)
        config: factory_workspace.WorkspaceRuntimeConfig | None = None
        target_path = self._resolve_target_dir_from_env(repo_root, resolved_env_file)

        try:
            config = stack.sync_workspace_runtime(
                repo_root,
                env_file=resolved_env_file,
                persist=False,
            )
            target_path = config.target_dir
            action = ["down", "-v", "--remove-orphans"]
            stack.run_compose_command(
                repo_root,
                stack.build_compose_command(repo_root, resolved_env_file, action),
            )
            print(
                f"🧹 Removed Docker stack and volumes for {config.factory_instance_id}"
            )
        except Exception as exc:  # noqa: BLE001
            print(
                "⚠️ Could not completely remove docker stack (it may not exist): "
                f"{exc}"
            )
            if config is None:
                config = self._build_runtime_config_for_target(target_path, repo_root)

        if resolved_env_file.exists():
            resolved_env_file.unlink()
            print(f"🧹 Deleted {resolved_env_file}")

        manifest_path = (
            target_path
            / factory_workspace.TMP_SUBPATH
            / factory_workspace.RUNTIME_MANIFEST_FILENAME
        )
        if manifest_path.exists():
            manifest_path.unlink()
            print(f"🧹 Deleted {manifest_path}")

        self._remove_runtime_data_dirs(config)
        self._persist_runtime_deleted_record(
            target_path=target_path,
            factory_dir=repo_root,
            config=config,
            trigger=normalized_trigger,
            reason_codes=normalized_reason_codes,
        )
        return 0

    def delete_runtime(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> int:
        return self.cleanup(
            repo_root,
            env_file=env_file,
            trigger=RuntimeActionTrigger.DELETE_RUNTIME,
            reason_codes=reason_codes,
        )

    def repair(
        self,
        repo_root: Path | None = None,
        *,
        env_file: Path | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> RepairResult:
        if repo_root is None:
            return RepairResult(
                attempted=False,
                success=False,
                reason_codes=(ReasonCode.MISSING_RUNTIME_METADATA,),
                details=(
                    "Repair requires the canonical factory repo root so the runtime "
                    "manager can assemble a snapshot and mutate runtime state.",
                ),
            )

        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        try:
            snapshot = self.build_snapshot(
                repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
            )
        except Exception as exc:  # noqa: BLE001
            return RepairResult(
                attempted=False,
                success=False,
                reason_codes=(ReasonCode.UNEXPECTED_ERROR,),
                details=(
                    "Unable to assemble a canonical runtime snapshot before repair: "
                    f"{exc}",
                ),
            )

        _, existing_record, _ = self._load_runtime_registry_entry(
            snapshot.instance_id,
            snapshot.target_dir,
        )
        existing_failure_count = self._coerce_int(
            (existing_record or {}).get("repair_failure_count"),
            default=0,
        )

        if existing_failure_count >= self._max_repair_failures:
            result = RepairResult(
                attempted=False,
                success=False,
                attempted_steps=(RepairStep.SURFACE_TERMINAL_FAILURE,),
                reason_codes=(
                    ReasonCode.REPAIR_CIRCUIT_BREAKER,
                    ReasonCode.TERMINAL_RUNTIME_FAILURE,
                ),
                details=(
                    "Bounded repair circuit-breaker is already tripped for this "
                    f"runtime after {existing_failure_count} failed repair attempt(s).",
                ),
                final_state=snapshot.lifecycle_state,
            )
            return self._finalize_repair_outcome(
                snapshot,
                result,
                existing_failure_count=existing_failure_count,
            )

        attempted_steps: list[RepairStep] = [RepairStep.REPROBE]
        reason_codes: list[ReasonCode] = [ReasonCode.REPAIR_REPROBE]
        details: list[str] = []

        readiness = snapshot.readiness
        if readiness is None:
            result = RepairResult(
                attempted=True,
                success=False,
                attempted_steps=tuple(attempted_steps),
                reason_codes=(ReasonCode.UNEXPECTED_ERROR,),
                details=("Runtime snapshot did not include a readiness result.",),
                final_state=snapshot.lifecycle_state,
            )
            return self._finalize_repair_outcome(
                snapshot,
                result,
                existing_failure_count=existing_failure_count,
            )

        if readiness.ready:
            result = RepairResult(
                attempted=True,
                success=True,
                attempted_steps=tuple(attempted_steps),
                reason_codes=tuple(reason_codes),
                details=(
                    "Runtime readiness succeeded during the initial re-probe; no "
                    "mutating repair step was necessary.",
                ),
                final_state=snapshot.lifecycle_state,
            )
            return self._finalize_repair_outcome(
                snapshot,
                result,
                existing_failure_count=existing_failure_count,
            )

        host_reason_code = self._classify_host_failure(snapshot)
        if host_reason_code is not None:
            result = RepairResult(
                attempted=True,
                success=False,
                attempted_steps=(
                    RepairStep.REPROBE,
                    RepairStep.SURFACE_TERMINAL_FAILURE,
                ),
                reason_codes=self._tuple_unique(
                    [
                        *reason_codes,
                        host_reason_code,
                        ReasonCode.TERMINAL_RUNTIME_FAILURE,
                    ]
                ),
                details=(
                    "Repair is blocked by a host-level runtime failure that must be "
                    "resolved outside the service-local repair ladder.",
                ),
                final_state=snapshot.lifecycle_state,
            )
            return self._finalize_repair_outcome(
                snapshot,
                result,
                existing_failure_count=existing_failure_count,
            )

        current_snapshot = snapshot

        if self._needs_restart(current_snapshot):
            targets = self._select_workspace_owned_targets(current_snapshot)
            attempted_steps.append(RepairStep.RESTART_SERVICE)
            reason_codes.append(ReasonCode.REPAIR_RESTART)
            details.append(
                "Attempting bounded service restart for: "
                f"{', '.join(targets) if targets else 'none'}"
            )
            next_snapshot, terminal_result = self._attempt_compose_repair_step(
                step=RepairStep.RESTART_SERVICE,
                action=["up", "-d", *targets],
                repo_root=repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
                current_snapshot=current_snapshot,
                attempted_steps=attempted_steps,
                reason_codes=reason_codes,
                details=details,
            )
            if terminal_result is not None:
                return self._finalize_repair_outcome(
                    current_snapshot,
                    terminal_result,
                    existing_failure_count=existing_failure_count,
                )
            if next_snapshot is not None:
                current_snapshot = next_snapshot
                if current_snapshot.readiness and current_snapshot.readiness.ready:
                    result = RepairResult(
                        attempted=True,
                        success=True,
                        attempted_steps=tuple(attempted_steps),
                        reason_codes=self._tuple_unique(reason_codes),
                        details=tuple(details),
                        final_state=current_snapshot.lifecycle_state,
                    )
                    return self._finalize_repair_outcome(
                        current_snapshot,
                        result,
                        existing_failure_count=existing_failure_count,
                    )

        if self._needs_recreate(current_snapshot):
            targets = self._select_workspace_owned_targets(current_snapshot)
            attempted_steps.append(RepairStep.RECREATE_SERVICE)
            reason_codes.append(ReasonCode.REPAIR_RECREATE)
            details.append(
                "Attempting bounded service recreation for: "
                f"{', '.join(targets) if targets else 'none'}"
            )
            next_snapshot, terminal_result = self._attempt_compose_repair_step(
                step=RepairStep.RECREATE_SERVICE,
                action=["up", "-d", "--force-recreate", "--no-deps", *targets],
                repo_root=repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
                current_snapshot=current_snapshot,
                attempted_steps=attempted_steps,
                reason_codes=reason_codes,
                details=details,
            )
            if terminal_result is not None:
                return self._finalize_repair_outcome(
                    current_snapshot,
                    terminal_result,
                    existing_failure_count=existing_failure_count,
                )
            if next_snapshot is not None:
                current_snapshot = next_snapshot
                if current_snapshot.readiness and current_snapshot.readiness.ready:
                    result = RepairResult(
                        attempted=True,
                        success=True,
                        attempted_steps=tuple(attempted_steps),
                        reason_codes=self._tuple_unique(reason_codes),
                        details=tuple(details),
                        final_state=current_snapshot.lifecycle_state,
                    )
                    return self._finalize_repair_outcome(
                        current_snapshot,
                        result,
                        existing_failure_count=existing_failure_count,
                    )

        if self._needs_dependency_repair(current_snapshot):
            dependencies = self._collect_dependency_targets(current_snapshot)
            if dependencies:
                attempted_steps.append(RepairStep.REPAIR_DEPENDENCY)
                reason_codes.append(ReasonCode.REPAIR_DEPENDENCY)
                details.append(
                    "Attempting dependency repair for: " f"{', '.join(dependencies)}"
                )
                next_snapshot, terminal_result = self._attempt_compose_repair_step(
                    step=RepairStep.REPAIR_DEPENDENCY,
                    action=["up", "-d", *dependencies],
                    repo_root=repo_root,
                    env_file=resolved_env_file,
                    selected_profiles=selected_profiles,
                    current_snapshot=current_snapshot,
                    attempted_steps=attempted_steps,
                    reason_codes=reason_codes,
                    details=details,
                )
                if terminal_result is not None:
                    return self._finalize_repair_outcome(
                        current_snapshot,
                        terminal_result,
                        existing_failure_count=existing_failure_count,
                    )
                if next_snapshot is not None:
                    current_snapshot = next_snapshot
                    if current_snapshot.readiness and current_snapshot.readiness.ready:
                        result = RepairResult(
                            attempted=True,
                            success=True,
                            attempted_steps=tuple(attempted_steps),
                            reason_codes=self._tuple_unique(reason_codes),
                            details=tuple(details),
                            final_state=current_snapshot.lifecycle_state,
                        )
                        return self._finalize_repair_outcome(
                            current_snapshot,
                            result,
                            existing_failure_count=existing_failure_count,
                        )

        if self._needs_metadata_reconcile(current_snapshot):
            attempted_steps.append(RepairStep.RECONCILE_METADATA)
            reason_codes.append(ReasonCode.REPAIR_RECONCILE_METADATA)
            details.append(
                "Reconciling runtime metadata/state drift through the authoritative "
                "workspace artifact sync path."
            )
            try:
                config = self._prepare_runtime_config_for_actions(
                    repo_root,
                    resolved_env_file,
                    current_snapshot,
                )
                factory_workspace.sync_runtime_artifacts(
                    config,
                    registry_path=self._registry_path,
                    runtime_state=current_snapshot.persisted_runtime_state,
                    active=current_snapshot.selection.active,
                )
            except Exception as exc:  # noqa: BLE001
                result = RepairResult(
                    attempted=True,
                    success=False,
                    attempted_steps=tuple(
                        [*attempted_steps, RepairStep.SURFACE_TERMINAL_FAILURE]
                    ),
                    reason_codes=self._tuple_unique(
                        [
                            *reason_codes,
                            self._classify_exception_reason_code(exc),
                            ReasonCode.TERMINAL_RUNTIME_FAILURE,
                        ]
                    ),
                    details=tuple(
                        [
                            *details,
                            "Runtime metadata reconciliation failed: " f"{exc}",
                        ]
                    ),
                    final_state=current_snapshot.lifecycle_state,
                )
                return self._finalize_repair_outcome(
                    current_snapshot,
                    result,
                    existing_failure_count=existing_failure_count,
                )

            current_snapshot = self.build_snapshot(
                repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
            )
            if current_snapshot.readiness and current_snapshot.readiness.ready:
                result = RepairResult(
                    attempted=True,
                    success=True,
                    attempted_steps=tuple(attempted_steps),
                    reason_codes=self._tuple_unique(reason_codes),
                    details=tuple(details),
                    final_state=current_snapshot.lifecycle_state,
                )
                return self._finalize_repair_outcome(
                    current_snapshot,
                    result,
                    existing_failure_count=existing_failure_count,
                )

        result = RepairResult(
            attempted=True,
            success=False,
            attempted_steps=tuple(
                [*attempted_steps, RepairStep.SURFACE_TERMINAL_FAILURE]
            ),
            reason_codes=self._tuple_unique(
                [
                    *reason_codes,
                    *(
                        current_snapshot.readiness.reason_codes
                        if current_snapshot.readiness
                        else ()
                    ),
                    ReasonCode.TERMINAL_RUNTIME_FAILURE,
                ]
            ),
            details=tuple(
                [
                    *details,
                    "Bounded repair exhausted the minimal ladder without restoring "
                    "runtime readiness.",
                ]
            ),
            final_state=current_snapshot.lifecycle_state,
        )
        return self._finalize_repair_outcome(
            current_snapshot,
            result,
            existing_failure_count=existing_failure_count,
        )

    def _build_selection_metadata(
        self,
        record: dict[str, Any],
        *,
        installed: bool,
        active: bool,
        profiles: Any,
    ) -> SelectionMetadata:
        return SelectionMetadata(
            installed=installed,
            active=active,
            profiles=profiles,
            activity_lease=self._build_lease_metadata(
                record,
                prefix="activity",
                kind=LeaseKind.ACTIVITY,
                default_present=active,
                default_renewed_at=self._coerce_optional_text(
                    record.get("last_activated_at")
                ),
            ),
            execution_lease=self._build_lease_metadata(
                record,
                prefix="execution",
                kind=LeaseKind.EXECUTION,
            ),
        )

    def _build_lease_metadata(
        self,
        record: dict[str, Any],
        *,
        prefix: str,
        kind: LeaseKind,
        default_present: bool = False,
        default_renewed_at: str | None = None,
    ) -> LeaseMetadata:
        present = self._coerce_bool(
            record.get(f"{prefix}_lease_present"), default_present
        )
        holder = self._coerce_optional_text(record.get(f"{prefix}_lease_holder")) or ""
        renewed_at = (
            self._coerce_optional_text(record.get(f"{prefix}_lease_renewed_at"))
            or default_renewed_at
        )
        expires_at = self._coerce_optional_text(
            record.get(f"{prefix}_lease_expires_at")
        )
        return LeaseMetadata(
            kind=kind,
            present=present,
            holder=holder,
            renewed_at=renewed_at,
            expires_at=expires_at,
        )

    def _build_recovery_metadata(
        self,
        snapshot: RuntimeSnapshot,
        record: dict[str, Any],
        readiness: ReadinessResult,
    ) -> RecoveryMetadata:
        last_trigger_raw = (
            self._coerce_optional_text(record.get("last_runtime_action")) or ""
        )
        last_trigger = None
        if last_trigger_raw:
            try:
                last_trigger = RuntimeActionTrigger(last_trigger_raw)
            except ValueError:
                last_trigger = None

        last_trigger_at = self._coerce_optional_text(
            record.get("last_runtime_action_at")
        )
        last_completed_tool_call_at = self._coerce_optional_text(
            record.get("last_completed_tool_call_boundary_at")
        )
        last_reason_codes = self._coerce_reason_codes(
            record.get("last_runtime_action_reason_codes", ())
        )
        repair_failure_count = self._coerce_int(
            record.get("repair_failure_count"),
            default=0,
        )
        circuit_breaker_tripped_at = self._coerce_optional_text(
            record.get("repair_circuit_breaker_tripped_at")
        )
        classification = RecoveryClassification.RESUME_SAFE

        if circuit_breaker_tripped_at or any(
            code
            in {
                ReasonCode.TERMINAL_RUNTIME_FAILURE,
                ReasonCode.REPAIR_CIRCUIT_BREAKER,
                ReasonCode.HOST_DOCKER_UNAVAILABLE,
                ReasonCode.HOST_NETWORK_UNAVAILABLE,
                ReasonCode.HOST_DISK_EXHAUSTED,
            }
            for code in last_reason_codes
        ):
            classification = RecoveryClassification.MANUAL_RECOVERY_REQUIRED
        elif snapshot.lifecycle_state in {
            RuntimeLifecycleState.STARTING,
            RuntimeLifecycleState.REPAIRING,
        } and (
            snapshot.selection.execution_lease
            and snapshot.selection.execution_lease.present
        ):
            classification = RecoveryClassification.RESUME_UNSAFE
        elif (
            not last_completed_tool_call_at
            and snapshot.selection.execution_lease
            and snapshot.selection.execution_lease.present
            and not readiness.ready
        ):
            classification = RecoveryClassification.RESUME_UNSAFE

        return RecoveryMetadata(
            classification=classification,
            completed_tool_call_boundary=bool(last_completed_tool_call_at),
            last_completed_tool_call_at=last_completed_tool_call_at,
            last_trigger=last_trigger,
            last_trigger_at=last_trigger_at,
            last_reason_codes=last_reason_codes,
            repair_failure_count=repair_failure_count,
            circuit_breaker_tripped=bool(circuit_breaker_tripped_at),
            circuit_breaker_tripped_at=circuit_breaker_tripped_at,
        )

    def _extract_record_transition_reason_codes(
        self,
        record: dict[str, Any],
        *,
        persisted_runtime_state: str,
        last_transition_at: str | None,
    ) -> tuple[ReasonCode, ...]:
        if not record:
            return ()
        last_action_at = self._coerce_optional_text(
            record.get("last_runtime_action_at")
        )
        if persisted_runtime_state == RuntimeLifecycleState.RUNTIME_DELETED.value:
            return self._coerce_reason_codes(
                record.get("last_runtime_action_reason_codes", ())
            )
        if last_action_at and last_action_at == last_transition_at:
            return self._coerce_reason_codes(
                record.get("last_runtime_action_reason_codes", ())
            )
        return ()

    def _normalize_runtime_action_trigger(
        self,
        trigger: RuntimeActionTrigger | str,
    ) -> RuntimeActionTrigger:
        if isinstance(trigger, RuntimeActionTrigger):
            return trigger
        return RuntimeActionTrigger(str(trigger).strip())

    def _coerce_reason_codes(
        self,
        raw_values: Iterable[ReasonCode | str] | Any,
    ) -> tuple[ReasonCode, ...]:
        if raw_values is None:
            return ()
        if isinstance(raw_values, (str, ReasonCode)):
            candidates: Iterable[ReasonCode | str] = (raw_values,)
        else:
            candidates = raw_values
        normalized: list[ReasonCode] = []
        for value in candidates:
            try:
                code = (
                    value
                    if isinstance(value, ReasonCode)
                    else ReasonCode(str(value).strip())
                )
            except ValueError:
                continue
            if code not in normalized:
                normalized.append(code)
        return tuple(normalized)

    def _coerce_bool(self, value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off", ""}:
                return False
        return bool(value)

    def _coerce_int(self, value: Any, *, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _coerce_optional_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in {"none", "null"}:
            return None
        return text

    def _build_runtime_config_for_target(
        self,
        target_path: Path,
        factory_dir: Path,
    ) -> factory_workspace.WorkspaceRuntimeConfig | None:
        try:
            return factory_workspace.build_runtime_config(
                target_path,
                factory_dir=factory_dir,
                registry_path=self._registry_path,
                reconcile_registry_before_allocating=False,
            )
        except Exception:  # noqa: BLE001
            return None

    def _remove_runtime_data_dirs(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig | None,
    ) -> None:
        if config is None:
            return
        try:
            data_dir_str = str(config.env_values.get("FACTORY_DATA_DIR", "")).strip()
            if not data_dir_str:
                return
            data_dir = Path(data_dir_str).expanduser()
            instance_memory_dir = data_dir / "memory" / config.factory_instance_id
            instance_bus_dir = data_dir / "bus" / config.factory_instance_id
            for instance_dir in (instance_memory_dir, instance_bus_dir):
                if instance_dir.exists() and instance_dir.is_dir():
                    shutil.rmtree(instance_dir, ignore_errors=True)
                    print(f"🧹 Erased data directory {instance_dir}")
        except Exception as exc:  # noqa: BLE001
            print(f"⚠️ Could not fully erase configured data directories: {exc}")

    def _load_runtime_registry_entry(
        self,
        instance_id: str,
        target_path: Path,
    ) -> tuple[str | None, dict[str, Any] | None, dict[str, Any]]:
        registry = factory_workspace.load_registry(self._registry_path)
        workspaces = registry.get("workspaces", {})
        if not isinstance(workspaces, dict):
            workspaces = {}
            registry["workspaces"] = workspaces

        if instance_id:
            record = workspaces.get(instance_id)
            if isinstance(record, dict):
                return instance_id, record, registry

        resolved_target = target_path.expanduser().resolve()
        for candidate_id, record in workspaces.items():
            if not isinstance(record, dict):
                continue
            raw_target = (
                self._coerce_optional_text(record.get("target_workspace_path")) or ""
            )
            if not raw_target:
                continue
            try:
                candidate_target = Path(raw_target).expanduser().resolve()
            except Exception:  # noqa: BLE001
                continue
            if candidate_target == resolved_target:
                return str(candidate_id), record, registry
        return None, None, registry

    def _persist_runtime_deleted_record(
        self,
        *,
        target_path: Path,
        factory_dir: Path,
        config: factory_workspace.WorkspaceRuntimeConfig | None,
        trigger: RuntimeActionTrigger,
        reason_codes: tuple[ReasonCode, ...],
    ) -> None:
        effective_config = config or self._build_runtime_config_for_target(
            target_path,
            factory_dir,
        )
        instance_id = (
            effective_config.factory_instance_id if effective_config is not None else ""
        )
        matched_instance_id, existing_record, registry = (
            self._load_runtime_registry_entry(
                instance_id,
                target_path,
            )
        )
        action_at = factory_workspace.utc_now_iso()

        if effective_config is not None:
            manifest = factory_workspace.build_runtime_manifest(effective_config)
            record = factory_workspace.build_registry_record_from_manifest(
                manifest,
                runtime_state=RuntimeLifecycleState.RUNTIME_DELETED.value,
                existing_record=existing_record,
            )
            instance_id = effective_config.factory_instance_id
        elif existing_record is not None:
            record = dict(existing_record)
            instance_id = (
                matched_instance_id
                or str(record.get("factory_instance_id", "")).strip()
            )
        else:
            return

        record["runtime_state"] = RuntimeLifecycleState.RUNTIME_DELETED.value
        record["updated_at"] = action_at
        record["last_runtime_action"] = trigger.value
        record["last_runtime_action_at"] = action_at
        record["last_runtime_action_reason_codes"] = [
            code.value for code in reason_codes
        ]
        record["last_completed_tool_call_boundary_at"] = action_at
        record["repair_failure_count"] = 0
        record["repair_circuit_breaker_tripped_at"] = None
        registry.setdefault("workspaces", {})[instance_id] = record
        if registry.get("active_workspace") == instance_id:
            registry["active_workspace"] = ""

        duplicate_ids = []
        resolved_target = target_path.expanduser().resolve()
        for candidate_id, candidate_record in registry["workspaces"].items():
            if candidate_id == instance_id or not isinstance(candidate_record, dict):
                continue
            raw_target = (
                self._coerce_optional_text(
                    candidate_record.get("target_workspace_path")
                )
                or ""
            )
            if not raw_target:
                continue
            try:
                candidate_target = Path(raw_target).expanduser().resolve()
            except Exception:  # noqa: BLE001
                continue
            if candidate_target == resolved_target:
                duplicate_ids.append(candidate_id)
        for duplicate_id in duplicate_ids:
            del registry["workspaces"][duplicate_id]

        factory_workspace.save_registry(registry, self._registry_path)

    def _prepare_runtime_config_for_actions(
        self,
        repo_root: Path,
        env_file: Path,
        snapshot: RuntimeSnapshot,
    ) -> factory_workspace.WorkspaceRuntimeConfig:
        stack = self._load_factory_stack_module()
        try:
            return stack.sync_workspace_runtime(
                repo_root,
                env_file=env_file,
                persist=False,
            )
        except Exception:  # noqa: BLE001
            config = self._build_runtime_config_for_target(
                snapshot.target_dir,
                snapshot.factory_dir,
            )
            if config is None:
                raise RuntimeError(
                    "Unable to prepare runtime configuration for bounded repair."
                )
            return config

    def _needs_restart(self, snapshot: RuntimeSnapshot) -> bool:
        readiness = snapshot.readiness
        if readiness is None:
            return False
        return bool(set(readiness.reason_codes) & _RESTART_REASON_CODES)

    def _needs_recreate(self, snapshot: RuntimeSnapshot) -> bool:
        readiness = snapshot.readiness
        if readiness is None:
            return False
        return bool(set(readiness.reason_codes) & _RECREATE_REASON_CODES)

    def _needs_dependency_repair(self, snapshot: RuntimeSnapshot) -> bool:
        readiness = snapshot.readiness
        if readiness is None:
            return False
        return ReasonCode.DEPENDENCY_UNHEALTHY in readiness.reason_codes

    def _needs_metadata_reconcile(self, snapshot: RuntimeSnapshot) -> bool:
        readiness = snapshot.readiness
        if readiness is None:
            return False
        return bool(set(readiness.reason_codes) & _METADATA_DRIFT_REASON_CODES)

    def _select_workspace_owned_targets(self, snapshot: RuntimeSnapshot) -> list[str]:
        readiness = snapshot.readiness
        blocking = list(readiness.blocking_services if readiness is not None else ())
        targets = [
            service_name
            for service_name in blocking
            if service_name in snapshot.services
            and snapshot.services[service_name].workspace_owned
        ]
        if targets:
            return targets
        return [
            service_name
            for service_name, record in snapshot.services.items()
            if record.workspace_owned
            and record.status
            in {
                ServiceInstanceStatus.DEGRADED,
                ServiceInstanceStatus.MISSING,
                ServiceInstanceStatus.STOPPED,
            }
        ]

    def _collect_dependency_targets(self, snapshot: RuntimeSnapshot) -> list[str]:
        catalog = snapshot.catalog or self.load_catalog()
        dependencies: list[str] = []
        for service_name in self._select_workspace_owned_targets(snapshot):
            entry = catalog.services.get(service_name)
            if entry is None:
                continue
            for dependency_name in entry.dependencies:
                record = snapshot.services.get(dependency_name)
                if record is not None and not record.workspace_owned:
                    continue
                if dependency_name not in dependencies:
                    dependencies.append(dependency_name)
        return dependencies

    def _attempt_compose_repair_step(
        self,
        *,
        step: RepairStep,
        action: list[str],
        repo_root: Path,
        env_file: Path,
        selected_profiles: Iterable[RuntimeProfileName | str] | None,
        current_snapshot: RuntimeSnapshot,
        attempted_steps: list[RepairStep],
        reason_codes: list[ReasonCode],
        details: list[str],
    ) -> tuple[RuntimeSnapshot | None, RepairResult | None]:
        if not action or len(action) <= 2:
            return current_snapshot, None

        try:
            self._run_compose_action(repo_root, env_file, action)
        except Exception as exc:  # noqa: BLE001
            terminal_reason = self._classify_exception_reason_code(exc)
            return None, RepairResult(
                attempted=True,
                success=False,
                attempted_steps=tuple(
                    [*attempted_steps, RepairStep.SURFACE_TERMINAL_FAILURE]
                ),
                reason_codes=self._tuple_unique(
                    [
                        *reason_codes,
                        terminal_reason,
                        ReasonCode.TERMINAL_RUNTIME_FAILURE,
                    ]
                ),
                details=tuple([*details, f"Repair step `{step.value}` failed: {exc}"]),
                final_state=current_snapshot.lifecycle_state,
            )

        self._sleep_with_backoff(step)
        try:
            next_snapshot = self.build_snapshot(
                repo_root,
                env_file=env_file,
                selected_profiles=selected_profiles,
            )
        except Exception as exc:  # noqa: BLE001
            terminal_reason = self._classify_exception_reason_code(exc)
            return None, RepairResult(
                attempted=True,
                success=False,
                attempted_steps=tuple(
                    [*attempted_steps, RepairStep.SURFACE_TERMINAL_FAILURE]
                ),
                reason_codes=self._tuple_unique(
                    [
                        *reason_codes,
                        terminal_reason,
                        ReasonCode.TERMINAL_RUNTIME_FAILURE,
                    ]
                ),
                details=tuple([*details, f"Post-repair re-probe failed: {exc}"]),
                final_state=current_snapshot.lifecycle_state,
            )
        return next_snapshot, None

    def _run_compose_action(
        self,
        repo_root: Path,
        env_file: Path,
        action: Sequence[str],
    ) -> None:
        stack = self._load_factory_stack_module()
        stack.run_compose_command(
            repo_root,
            stack.build_compose_command(repo_root, env_file, action),
        )

    def _sleep_with_backoff(self, step: RepairStep) -> None:
        del step
        delay = self._repair_backoff_seconds[0] if self._repair_backoff_seconds else 0.0
        if delay > 0:
            self._sleep_func(delay)

    def _classify_host_failure(
        self,
        snapshot: RuntimeSnapshot,
    ) -> ReasonCode | None:
        readiness = snapshot.readiness
        if readiness is None:
            return None
        if readiness.status == ReadinessStatus.DOCKER_UNAVAILABLE:
            return ReasonCode.HOST_DOCKER_UNAVAILABLE
        if readiness.status == ReadinessStatus.DOCKER_ERROR:
            return self._classify_exception_reason_code(snapshot.inventory_error or "")
        return None

    def _classify_exception_reason_code(self, exc: Any) -> ReasonCode:
        text = str(exc).lower()
        if "docker" in text and (
            "daemon" in text or "not found" in text or "no such file" in text
        ):
            return ReasonCode.HOST_DOCKER_UNAVAILABLE
        if "network" in text:
            return ReasonCode.HOST_NETWORK_UNAVAILABLE
        if "no space" in text or "disk" in text:
            return ReasonCode.HOST_DISK_EXHAUSTED
        return ReasonCode.UNEXPECTED_ERROR

    def _finalize_repair_outcome(
        self,
        snapshot: RuntimeSnapshot,
        result: RepairResult,
        *,
        existing_failure_count: int,
    ) -> RepairResult:
        if (
            not result.success
            and ReasonCode.REPAIR_CIRCUIT_BREAKER not in result.reason_codes
            and existing_failure_count + (1 if result.attempted else 0)
            >= self._max_repair_failures
        ):
            result = replace(
                result,
                reason_codes=self._tuple_unique(
                    [*result.reason_codes, ReasonCode.REPAIR_CIRCUIT_BREAKER]
                ),
                details=tuple(
                    [
                        *result.details,
                        "Bounded repair circuit-breaker tripped after "
                        f"{existing_failure_count + 1} failed repair attempt(s).",
                    ]
                ),
            )
        self._persist_repair_outcome(
            snapshot,
            result,
            existing_failure_count=existing_failure_count,
        )
        return result

    def _persist_repair_outcome(
        self,
        snapshot: RuntimeSnapshot,
        result: RepairResult,
        *,
        existing_failure_count: int,
    ) -> None:
        effective_state = result.final_state or snapshot.lifecycle_state
        matched_instance_id, existing_record, registry = (
            self._load_runtime_registry_entry(
                snapshot.instance_id,
                snapshot.target_dir,
            )
        )
        effective_config = self._build_runtime_config_for_target(
            snapshot.target_dir,
            snapshot.factory_dir,
        )
        action_at = factory_workspace.utc_now_iso()

        if effective_config is not None:
            manifest = factory_workspace.build_runtime_manifest(effective_config)
            record = factory_workspace.build_registry_record_from_manifest(
                manifest,
                runtime_state=effective_state.value,
                existing_record=existing_record,
            )
            instance_id = effective_config.factory_instance_id
        elif existing_record is not None:
            record = dict(existing_record)
            instance_id = matched_instance_id or snapshot.instance_id
        else:
            return

        existing_circuit_breaker_tripped_at = self._coerce_optional_text(
            record.get("repair_circuit_breaker_tripped_at")
        )
        if result.success:
            repair_failure_count = 0
        elif (
            ReasonCode.REPAIR_CIRCUIT_BREAKER in result.reason_codes
            and not result.attempted
        ):
            repair_failure_count = existing_failure_count
        else:
            repair_failure_count = existing_failure_count + 1

        circuit_breaker_tripped_at = None
        if (
            ReasonCode.REPAIR_CIRCUIT_BREAKER in result.reason_codes
            or repair_failure_count >= self._max_repair_failures
        ):
            circuit_breaker_tripped_at = (
                existing_circuit_breaker_tripped_at or action_at
            )

        record["runtime_state"] = effective_state.value
        record["updated_at"] = action_at
        record["last_runtime_action"] = RuntimeActionTrigger.REPAIR.value
        record["last_runtime_action_at"] = action_at
        record["last_runtime_action_reason_codes"] = [
            code.value for code in result.reason_codes
        ]
        record["last_completed_tool_call_boundary_at"] = action_at
        record["repair_failure_count"] = repair_failure_count
        record["repair_circuit_breaker_tripped_at"] = circuit_breaker_tripped_at
        registry.setdefault("workspaces", {})[instance_id] = record
        factory_workspace.save_registry(registry, self._registry_path)

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

    def _extract_named_urls_from_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        mappings: dict[str, tuple[str, str]],
    ) -> dict[str, str]:
        urls: dict[str, str] = {}
        for server_name, (section_name, runtime_name) in mappings.items():
            normalized_section_name = {
                "runtime_health": "manifest_health_urls",
                "mcp_servers": "manifest_server_urls",
            }.get(section_name, section_name)
            section = getattr(snapshot, normalized_section_name, {})
            url = (
                str(section.get(runtime_name, "")).strip()
                if isinstance(section, dict)
                else ""
            )
            if url:
                urls[server_name] = url
        return urls

    def _extract_named_urls_from_manifest(
        self,
        manifest: dict[str, Any],
        mappings: dict[str, tuple[str, str]],
    ) -> dict[str, str]:
        urls: dict[str, str] = {}
        for server_name, (section_name, runtime_name) in mappings.items():
            normalized_section_name = {
                "manifest_health_urls": "runtime_health",
                "manifest_server_urls": "mcp_servers",
            }.get(section_name, section_name)
            section = manifest.get(normalized_section_name, {})
            entry = section.get(runtime_name, {}) if isinstance(section, dict) else {}
            if isinstance(entry, dict):
                url = str(entry.get("url", "")).strip()
                if url:
                    urls[server_name] = url
        return urls

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

    def _missing_required_config_keys(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        entry: ServiceCatalogEntry,
    ) -> list[str]:
        missing_keys: list[str] = []
        for config_key in entry.required_config_keys:
            if str(config.env_values.get(config_key, "")).strip():
                continue
            missing_keys.append(config_key)
        return missing_keys

    def _missing_required_mount_paths(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        entry: ServiceCatalogEntry,
    ) -> list[tuple[str, Path]]:
        missing_mounts: list[tuple[str, Path]] = []
        for mount_spec in entry.required_mounts:
            resolved_mount_path = self._resolve_required_mount_path(config, mount_spec)
            if resolved_mount_path is not None and resolved_mount_path.exists():
                continue
            missing_mounts.append(
                (
                    mount_spec,
                    (
                        resolved_mount_path
                        if resolved_mount_path is not None
                        else Path(mount_spec)
                    ),
                )
            )
        return missing_mounts

    def _resolve_required_mount_path(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        mount_spec: str,
    ) -> Path | None:
        resolved_spec = (
            mount_spec.replace("<factory_instance_id>", config.factory_instance_id)
            .replace("<project_workspace_id>", config.project_workspace_id)
            .strip()
        )
        if not resolved_spec:
            return None

        if resolved_spec.startswith("FACTORY_DATA_DIR/"):
            base_dir = str(config.env_values.get("FACTORY_DATA_DIR", "")).strip()
            if not base_dir:
                return None
            relative_mount = resolved_spec.removeprefix("FACTORY_DATA_DIR/")
            return (Path(base_dir).expanduser().resolve() / relative_mount).resolve()

        return Path(resolved_spec).expanduser().resolve()

    def _classify_required_config_reason(self, config_key: str) -> ReasonCode:
        normalized_key = config_key.strip().lower()
        if any(token in normalized_key for token in _SECRET_KEY_TOKENS):
            return ReasonCode.MISSING_SECRET
        return ReasonCode.MISSING_CONFIG

    def _probe_http_url(
        self,
        url: str,
        *,
        allow_http_error: bool,
    ) -> str | None:
        if self._http_probe_func is not None:
            return self._http_probe_func(
                url,
                self._readiness_probe_timeout,
                allow_http_error,
            )

        try:
            with urlopen(url, timeout=self._readiness_probe_timeout):
                return None
        except RemoteDisconnected:
            if allow_http_error:
                return None
            return "remote disconnected before response"
        except HTTPError as exc:
            if allow_http_error:
                return None
            return f"HTTP {exc.code}"
        except URLError as exc:
            return str(exc.reason)

    def _probe_mcp_initialize(
        self,
        endpoint_url: str,
        *,
        workspace_id: str,
    ) -> str | None:
        normalized_endpoint = self._normalize_mcp_endpoint(endpoint_url)
        if self._mcp_initialize_probe is not None:
            return self._mcp_initialize_probe(
                normalized_endpoint,
                self._readiness_probe_timeout,
                workspace_id,
            )

        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": DEFAULT_MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "software-factory-runtime-manager",
                        "version": "1.0",
                    },
                },
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": MCP_ACCEPT_HEADER,
            MCP_PROTOCOL_VERSION_HEADER: DEFAULT_MCP_PROTOCOL_VERSION,
        }
        if workspace_id.strip():
            headers[factory_workspace.WORKSPACE_ID_HEADER] = workspace_id.strip()

        request = Request(
            normalized_endpoint,
            data=payload,
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=self._readiness_probe_timeout) as response:
                raw_body = response.read().decode("utf-8")
                _ = response.headers.get(MCP_SESSION_ID_HEADER)
        except RemoteDisconnected:
            return "remote disconnected before initialize response"
        except HTTPError as exc:
            return f"HTTP {exc.code}"
        except URLError as exc:
            return str(exc.reason)

        try:
            data = json.loads(raw_body) if raw_body.strip() else {}
        except (json.JSONDecodeError, ValueError) as exc:
            return f"invalid JSON response ({exc})"

        if not isinstance(data, dict):
            return "initialize response was not a JSON object"
        if "error" in data:
            error = data.get("error")
            if isinstance(error, dict):
                code = error.get("code")
                message = error.get("message")
                return f"[{code}] {message}"
            return str(error)
        if "result" not in data:
            return "initialize response did not include a result payload"
        return None

    def _normalize_mcp_endpoint(self, endpoint_url: str) -> str:
        normalized_endpoint = endpoint_url.strip().rstrip("/")
        if not normalized_endpoint:
            return normalized_endpoint
        if normalized_endpoint.endswith("/mcp"):
            return normalized_endpoint
        return f"{normalized_endpoint}/mcp"

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
        if persisted_runtime_state == RuntimeLifecycleState.RUNTIME_DELETED.value:
            return RuntimeLifecycleState.RUNTIME_DELETED
        if persisted_runtime_state == "starting":
            return RuntimeLifecycleState.STARTING
        if persisted_runtime_state == RuntimeLifecycleState.REPAIRING.value:
            return RuntimeLifecycleState.REPAIRING
        if persisted_runtime_state == RuntimeLifecycleState.SUSPENDED.value:
            return RuntimeLifecycleState.SUSPENDED
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
        if self._stack_module_loader is not None:
            return self._stack_module_loader()
        return importlib.import_module("factory_stack")

    def _tuple_unique(
        self,
        values: Iterable[ReasonCode],
    ) -> tuple[ReasonCode, ...]:
        return tuple(dict.fromkeys(values))
