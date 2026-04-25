"""Authoritative MCP runtime-manager contract.

This phase-1 implementation establishes one dedicated runtime-truth surface
outside the harness layer, as sequenced by
`docs/architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md` and governed by
`ADR-013`, `ADR-014`, `ADR-009`, and `ADR-012`.
"""

from __future__ import annotations

import hashlib
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
    RuntimeMode,
    RuntimeProfileName,
    RuntimeSnapshot,
    SelectionMetadata,
    ServiceCatalogEntry,
    ServiceInstanceStatus,
    ServiceRuntimeRecord,
)
from factory_runtime.secret_safety import (
    is_blank_or_placeholder,
    is_placeholder_repo_list,
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
_PRODUCTION_GITHUB_CREDENTIAL_ENV_KEYS = (
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "GITHUB_PAT",
)
_LLM_CONFIG_PATH_ENV_KEY = "LLM_CONFIG_PATH"
_LLM_OVERRIDE_PATH_ENV_KEY = "LLM_OVERRIDE_PATH"
_GITHUB_OPS_ALLOWED_REPOS_ENV_KEY = "GITHUB_OPS_ALLOWED_REPOS"
BACKUP_BUNDLES_DIRNAME = "backups"
BACKUP_BUNDLE_PREFIX = "backup-"
BACKUP_MANIFEST_FILENAME = "bundle-manifest.json"
BACKUP_CHECKSUMS_FILENAME = "checksums.sha256"
_RESTORE_REQUIRED_ARTIFACTS = {
    "memory-db",
    "agent-bus-db",
    "factory-env",
    "runtime-manifest",
    "runtime-snapshot",
    "workspace-registry",
}


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
        resolved_workspace_file = workspace_file or self._default_workspace_file
        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        target_dir = self._resolve_target_dir_from_env(repo_root, resolved_env_file)
        config = factory_workspace.build_runtime_config(
            target_dir,
            factory_dir=repo_root,
            workspace_file=resolved_workspace_file,
            registry_path=self._registry_path,
        )
        runtime_mode = self._resolve_runtime_mode(config)
        profile_selection = catalog.select_profiles(
            self._resolve_selected_profiles_for_runtime_mode(
                runtime_mode,
                selected_profiles,
            )
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
        persisted_runtime_state = self._normalize_supported_runtime_state(
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
            runtime_mode=runtime_mode,
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

    def _resolve_runtime_mode(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> RuntimeMode:
        normalized_mode = factory_workspace.normalize_runtime_mode(config.runtime_mode)
        try:
            return RuntimeMode(normalized_mode)
        except ValueError:
            return RuntimeMode.DEVELOPMENT

    def _resolve_selected_profiles_for_runtime_mode(
        self,
        runtime_mode: RuntimeMode,
        selected_profiles: Iterable[RuntimeProfileName | str] | None,
    ) -> Iterable[RuntimeProfileName | str] | None:
        if selected_profiles is not None:
            return selected_profiles
        if runtime_mode == RuntimeMode.PRODUCTION:
            return (RuntimeProfileName.WORKSPACE_PRODUCTION,)
        return None

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

        if resolved_config is not None:
            production_issues, production_codes = self._production_config_issues(
                resolved_config,
                profile_services,
            )
            if production_issues:
                config_drift_issues.extend(production_issues)
                config_drift_codes.extend(production_codes)

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
            recommended_action = RecommendedAction.START
            issues = (
                "Runtime preflight detected no running containers for compose "
                f"project `{snapshot.compose_project_name}`. Infrastructure needs "
                "ramp-up via `factory_stack.py start`.",
            )
            if snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED:
                recommended_action = RecommendedAction.RESUME
                issues = (
                    "Runtime preflight detected a bounded `suspended` runtime with no "
                    "running containers. Resume it via `factory_stack.py resume` to "
                    "re-hydrate services while preserving recovery metadata.",
                )
            return ReadinessResult(
                status=ReadinessStatus.NEEDS_RAMP_UP,
                recommended_action=recommended_action,
                ready=False,
                reason_codes=(ReasonCode.NO_RUNNING_SERVICES,),
                issues=issues,
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

    def suspend(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        completed_tool_call_boundary: bool = False,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> RuntimeSnapshot:
        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        snapshot = self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

        if not snapshot.selection.installed:
            raise RuntimeError(
                "Cannot suspend a runtime that is not installed in the canonical registry."
            )
        if snapshot.lifecycle_state == RuntimeLifecycleState.RUNTIME_DELETED:
            raise RuntimeError(
                "Cannot suspend a runtime that has already been deleted."
            )
        if snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED:
            return snapshot
        if snapshot.lifecycle_state != RuntimeLifecycleState.RUNNING:
            raise RuntimeError(
                "Suspend is only supported from the bounded `running` lifecycle state; "
                f"current state is `{snapshot.lifecycle_state.value}`."
            )
        if snapshot.readiness is None or not snapshot.readiness.ready:
            raise RuntimeError(
                "Suspend requires a ready runtime. Repair or start the runtime until "
                "readiness succeeds before entering `suspended`."
            )

        self.stop(
            repo_root,
            env_file=resolved_env_file,
            preserve_runtime_state=True,
        )
        action_at = factory_workspace.utc_now_iso()
        merged_reason_codes = self._tuple_unique(
            [
                ReasonCode.SUSPEND_REQUESTED,
                *self._coerce_reason_codes(reason_codes),
            ]
        )
        self._persist_runtime_action_metadata(
            snapshot=snapshot,
            runtime_state=RuntimeLifecycleState.SUSPENDED,
            trigger=RuntimeActionTrigger.SUSPEND,
            action_at=action_at,
            reason_codes=merged_reason_codes,
            completed_tool_call_boundary_at=(
                action_at if completed_tool_call_boundary else None
            ),
            clear_repair_failure_state=True,
        )
        return self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

    def resume(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
        wait: bool = True,
        wait_timeout: int = 300,
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> RuntimeSnapshot:
        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        snapshot = self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

        if snapshot.lifecycle_state != RuntimeLifecycleState.SUSPENDED:
            raise RuntimeError(
                "Resume is only supported from the bounded `suspended` lifecycle state; "
                f"current state is `{snapshot.lifecycle_state.value}`."
            )
        if snapshot.recovery and (
            snapshot.recovery.classification
            == RecoveryClassification.MANUAL_RECOVERY_REQUIRED
        ):
            raise RuntimeError(
                "Cannot resume a suspended runtime that requires manual recovery."
            )

        self.start(
            repo_root,
            env_file=resolved_env_file,
            build=False,
            wait=wait,
            wait_timeout=wait_timeout,
        )
        resumed_snapshot = self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

        merged_reason_codes: list[ReasonCode] = [
            ReasonCode.RESUME_REQUESTED,
            *self._coerce_reason_codes(reason_codes),
        ]
        if resumed_snapshot.readiness and not resumed_snapshot.readiness.ready:
            repair_result = self.repair(
                repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
            )
            if repair_result.attempted:
                merged_reason_codes.append(ReasonCode.RESUME_REPAIR_ATTEMPTED)
                merged_reason_codes.extend(repair_result.reason_codes)
            resumed_snapshot = self.build_snapshot(
                repo_root,
                env_file=resolved_env_file,
                selected_profiles=selected_profiles,
            )

        action_at = factory_workspace.utc_now_iso()
        merged_reason_codes = list(
            self._tuple_unique(
                [
                    *merged_reason_codes,
                    *(
                        resumed_snapshot.readiness.reason_codes
                        if resumed_snapshot.readiness is not None
                        else ()
                    ),
                ]
            )
        )
        completed_tool_call_boundary_at = (
            snapshot.recovery.last_completed_tool_call_at
            if snapshot.recovery is not None
            else None
        )
        self._persist_runtime_action_metadata(
            snapshot=resumed_snapshot,
            runtime_state=resumed_snapshot.lifecycle_state,
            trigger=RuntimeActionTrigger.RESUME,
            action_at=action_at,
            reason_codes=merged_reason_codes,
            completed_tool_call_boundary_at=completed_tool_call_boundary_at,
            clear_repair_failure_state=(
                resumed_snapshot.readiness is not None
                and resumed_snapshot.readiness.ready
            ),
        )
        return self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

    def backup(
        self,
        repo_root: Path,
        *,
        env_file: Path | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> dict[str, Any]:
        resolved_env_file = self.resolve_env_file(repo_root, env_file)
        snapshot = self.build_snapshot(
            repo_root,
            env_file=resolved_env_file,
            selected_profiles=selected_profiles,
        )

        if not snapshot.selection.installed:
            raise RuntimeError(
                "Cannot back up a runtime that is not installed in the canonical registry."
            )
        if snapshot.lifecycle_state != RuntimeLifecycleState.SUSPENDED:
            raise RuntimeError(
                "Supported runtime backup requires the bounded `suspended` lifecycle "
                "state. Suspend a ready runtime first via `factory_stack.py suspend`; "
                f"current state is `{snapshot.lifecycle_state.value}`."
            )

        config = self._prepare_runtime_config_for_actions(
            repo_root,
            resolved_env_file,
            snapshot,
        )
        data_root = self._resolve_factory_data_dir(config)
        bundle_created_at = factory_workspace.utc_now_iso()
        bundle_dir = self._create_backup_bundle_dir(
            data_root,
            config.factory_instance_id,
            bundle_created_at,
        )
        artifact_specs: list[dict[str, str]] = []

        try:
            copy_specs = [
                (
                    "memory-db",
                    data_root / "memory" / config.factory_instance_id / "memory.db",
                    Path("data") / "memory" / config.factory_instance_id / "memory.db",
                ),
                (
                    "agent-bus-db",
                    data_root / "bus" / config.factory_instance_id / "agent_bus.db",
                    Path("data") / "bus" / config.factory_instance_id / "agent_bus.db",
                ),
                (
                    "factory-env",
                    resolved_env_file,
                    Path("workspace")
                    / factory_workspace.FACTORY_DIRNAME
                    / ".factory.env",
                ),
                (
                    "runtime-manifest",
                    config.runtime_manifest_path,
                    Path("workspace")
                    / factory_workspace.TMP_SUBPATH
                    / factory_workspace.RUNTIME_MANIFEST_FILENAME,
                ),
            ]
            missing_sources = [
                str(source_path)
                for _logical_name, source_path, _relative_path in copy_specs
                if not source_path.exists()
            ]
            if missing_sources:
                raise RuntimeError(
                    "Supported runtime backup requires all canonical state files to "
                    "exist. Missing: " + ", ".join(missing_sources)
                )

            for logical_name, source_path, relative_path in copy_specs:
                destination = bundle_dir / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, destination)
                artifact_specs.append(
                    {
                        "logical_name": logical_name,
                        "source_path": str(source_path.resolve()),
                        "bundle_relative_path": relative_path.as_posix(),
                    }
                )

            registry_snapshot = self._build_backup_registry_snapshot(snapshot, config)
            generated_artifacts = [
                (
                    "runtime-snapshot",
                    Path("metadata") / "runtime-snapshot.json",
                    snapshot.as_dict(),
                ),
                (
                    "workspace-registry",
                    Path("metadata") / "workspace-registry.json",
                    registry_snapshot,
                ),
            ]
            for logical_name, relative_path, payload in generated_artifacts:
                destination = bundle_dir / relative_path
                factory_workspace.write_json_atomic(destination, payload)
                artifact_specs.append(
                    {
                        "logical_name": logical_name,
                        "source_path": "",
                        "bundle_relative_path": relative_path.as_posix(),
                    }
                )

            artifacts: list[dict[str, Any]] = []
            checksum_lines: list[str] = []
            for artifact in artifact_specs:
                relative_path = Path(artifact["bundle_relative_path"])
                bundled_path = bundle_dir / relative_path
                sha256 = self._sha256_file(bundled_path)
                checksum_lines.append(f"{sha256}  {relative_path.as_posix()}")
                artifacts.append(
                    {
                        **artifact,
                        "sha256": sha256,
                        "size_bytes": bundled_path.stat().st_size,
                    }
                )

            checksums_path = bundle_dir / BACKUP_CHECKSUMS_FILENAME
            checksums_path.write_text(
                "\n".join(checksum_lines) + "\n",
                encoding="utf-8",
            )

            recovery_classification = (
                snapshot.recovery.classification.value
                if snapshot.recovery is not None
                else ""
            )
            completed_tool_call_boundary = bool(
                snapshot.recovery.completed_tool_call_boundary
                if snapshot.recovery is not None
                else False
            )
            manifest = {
                "schema_version": 1,
                "bundle_created_at": bundle_created_at,
                "workspace_id": snapshot.workspace_id,
                "instance_id": snapshot.instance_id,
                "compose_project_name": snapshot.compose_project_name,
                "target_dir": str(snapshot.target_dir),
                "factory_dir": str(snapshot.factory_dir),
                "factory_data_dir": str(data_root),
                "runtime_mode": snapshot.runtime_mode.value,
                "runtime_state": snapshot.lifecycle_state.value,
                "required_precondition": RuntimeLifecycleState.SUSPENDED.value,
                "shared_mode": snapshot.shared_mode,
                "recovery_classification": recovery_classification,
                "completed_tool_call_boundary": completed_tool_call_boundary,
                "selected_profiles": [
                    profile.value for profile in snapshot.selection.profiles.names
                ],
                "checksums_file": BACKUP_CHECKSUMS_FILENAME,
                "artifacts": artifacts,
            }
            factory_workspace.write_json_atomic(
                bundle_dir / BACKUP_MANIFEST_FILENAME,
                manifest,
            )
        except Exception:
            shutil.rmtree(bundle_dir, ignore_errors=True)
            raise

        merged_reason_codes = self._tuple_unique(
            [
                ReasonCode.BACKUP_REQUESTED,
                *self._coerce_reason_codes(reason_codes),
            ]
        )
        self._persist_runtime_action_metadata(
            snapshot=snapshot,
            runtime_state=RuntimeLifecycleState.SUSPENDED,
            trigger=RuntimeActionTrigger.BACKUP,
            action_at=factory_workspace.utc_now_iso(),
            reason_codes=merged_reason_codes,
            completed_tool_call_boundary_at=(
                snapshot.recovery.last_completed_tool_call_at
                if snapshot.recovery is not None
                else None
            ),
        )

        return {
            "workspace_id": snapshot.workspace_id,
            "instance_id": snapshot.instance_id,
            "runtime_state": snapshot.lifecycle_state.value,
            "required_precondition": RuntimeLifecycleState.SUSPENDED.value,
            "bundle_created_at": bundle_created_at,
            "bundle_path": str(bundle_dir),
            "manifest_path": str(bundle_dir / BACKUP_MANIFEST_FILENAME),
            "checksums_path": str(bundle_dir / BACKUP_CHECKSUMS_FILENAME),
            "captured_artifact_count": len(artifact_specs),
            "recovery_classification": recovery_classification,
            "completed_tool_call_boundary": completed_tool_call_boundary,
        }

    def restore(
        self,
        repo_root: Path,
        *,
        bundle_path: Path,
        env_file: Path | None = None,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
        reason_codes: Iterable[ReasonCode | str] | None = None,
    ) -> dict[str, Any]:
        resolved_repo_root = repo_root.expanduser().resolve()
        resolved_bundle_path = bundle_path.expanduser().resolve()
        bundle_manifest = self._load_restore_bundle_manifest(resolved_bundle_path)
        artifact_catalog = self._validate_restore_bundle_artifacts(
            resolved_bundle_path,
            bundle_manifest,
        )
        bundled_env_values = factory_workspace.parse_env_file(
            artifact_catalog["factory-env"]["path"]
        )
        bundled_runtime_manifest = self._load_json_object(
            artifact_catalog["runtime-manifest"]["path"],
            label="bundled runtime manifest",
        )
        bundled_runtime_snapshot = self._load_json_object(
            artifact_catalog["runtime-snapshot"]["path"],
            label="bundled runtime snapshot",
        )
        bundled_registry_snapshot = self._load_json_object(
            artifact_catalog["workspace-registry"]["path"],
            label="bundled workspace registry snapshot",
        )

        restore_config = self._build_restore_config(
            resolved_repo_root,
            bundled_env_values,
            bundled_runtime_manifest,
        )
        resolved_env_file = self.resolve_env_file(resolved_repo_root, env_file)
        expected_env_file = (
            restore_config.target_dir
            / factory_workspace.FACTORY_DIRNAME
            / ".factory.env"
        )
        if resolved_env_file != expected_env_file:
            raise RuntimeError(
                "Supported runtime restore requires the canonical installed-workspace "
                f"env path `{expected_env_file}`, but received `{resolved_env_file}`."
            )

        self._validate_restore_bundle_identity(
            repo_root=resolved_repo_root,
            config=restore_config,
            bundle_manifest=bundle_manifest,
            bundled_env_values=bundled_env_values,
            bundled_runtime_manifest=bundled_runtime_manifest,
            bundled_runtime_snapshot=bundled_runtime_snapshot,
            bundled_registry_snapshot=bundled_registry_snapshot,
        )
        self._validate_restore_port_safety(restore_config)
        self._validate_restore_runtime_stopped(restore_config.compose_project_name)

        data_root = self._resolve_factory_data_dir(restore_config)
        restore_targets = [
            (
                artifact_catalog["memory-db"]["path"],
                data_root / "memory" / restore_config.factory_instance_id / "memory.db",
            ),
            (
                artifact_catalog["agent-bus-db"]["path"],
                data_root / "bus" / restore_config.factory_instance_id / "agent_bus.db",
            ),
        ]

        for source_path, destination_path in restore_targets:
            self._restore_bundle_file(source_path, destination_path)

        factory_workspace.sync_runtime_artifacts(
            restore_config,
            registry_path=self._registry_path,
            runtime_state=RuntimeLifecycleState.SUSPENDED.value,
            active=None,
        )

        restored_snapshot = self.build_snapshot(
            resolved_repo_root,
            env_file=expected_env_file,
            selected_profiles=selected_profiles,
        )
        restore_boundary_at = self._resolve_restore_boundary_timestamp(
            bundle_manifest,
            bundled_runtime_snapshot,
            bundled_registry_snapshot,
        )
        merged_reason_codes = self._tuple_unique(
            [
                ReasonCode.RESTORE_REQUESTED,
                *self._coerce_reason_codes(reason_codes),
            ]
        )
        self._persist_runtime_action_metadata(
            snapshot=restored_snapshot,
            runtime_state=RuntimeLifecycleState.SUSPENDED,
            trigger=RuntimeActionTrigger.RESTORE,
            action_at=factory_workspace.utc_now_iso(),
            reason_codes=merged_reason_codes,
            completed_tool_call_boundary_at=restore_boundary_at,
            clear_repair_failure_state=True,
        )
        restored_snapshot = self.build_snapshot(
            resolved_repo_root,
            env_file=expected_env_file,
            selected_profiles=selected_profiles,
        )
        restored_readiness = restored_snapshot.readiness
        restored_recovery = restored_snapshot.recovery

        return {
            "workspace_id": restored_snapshot.workspace_id,
            "instance_id": restored_snapshot.instance_id,
            "runtime_state": restored_snapshot.lifecycle_state.value,
            "bundle_path": str(resolved_bundle_path),
            "restored_artifact_count": len(restore_targets) + 2,
            "preflight_status": (
                restored_readiness.status.value
                if restored_readiness is not None
                else ""
            ),
            "recommended_action": (
                restored_readiness.recommended_action.value
                if restored_readiness is not None
                else ""
            ),
            "recovery_classification": (
                restored_recovery.classification.value
                if restored_recovery is not None
                else ""
            ),
            "completed_tool_call_boundary": bool(
                restored_recovery.completed_tool_call_boundary
                if restored_recovery is not None
                else False
            ),
        }

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
        print(
            "🧹 "
            f"`{normalized_trigger.value}` removed workspace containers and named "
            "volumes when present, generated runtime metadata, registry ownership, "
            "and workspace-scoped runtime data. The installed baseline and Docker "
            "images were retained."
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

    def _persist_runtime_action_metadata(
        self,
        *,
        snapshot: RuntimeSnapshot,
        runtime_state: RuntimeLifecycleState | str,
        trigger: RuntimeActionTrigger,
        action_at: str,
        reason_codes: Iterable[ReasonCode | str] | None = None,
        completed_tool_call_boundary_at: str | None = None,
        clear_repair_failure_state: bool = False,
    ) -> None:
        effective_state = (
            runtime_state.value
            if isinstance(runtime_state, RuntimeLifecycleState)
            else str(runtime_state).strip()
        )
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
        if effective_config is not None:
            manifest = factory_workspace.build_runtime_manifest(effective_config)
            record = factory_workspace.build_registry_record_from_manifest(
                manifest,
                runtime_state=effective_state,
                existing_record=existing_record,
            )
            instance_id = effective_config.factory_instance_id
        elif existing_record is not None:
            record = dict(existing_record)
            instance_id = matched_instance_id or snapshot.instance_id
        else:
            return

        record["runtime_state"] = effective_state
        record["updated_at"] = action_at
        record["last_runtime_action"] = trigger.value
        record["last_runtime_action_at"] = action_at
        record["last_runtime_action_reason_codes"] = [
            code.value for code in self._coerce_reason_codes(reason_codes)
        ]
        record["last_completed_tool_call_boundary_at"] = completed_tool_call_boundary_at
        if clear_repair_failure_state:
            record["repair_failure_count"] = 0
            record["repair_circuit_breaker_tripped_at"] = None

        registry.setdefault("workspaces", {})[instance_id] = record
        factory_workspace.save_registry(registry, self._registry_path)

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

    def _production_config_issues(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        profile_services: Sequence[str],
    ) -> tuple[list[str], list[ReasonCode]]:
        if (
            factory_workspace.normalize_runtime_mode(config.runtime_mode)
            != factory_workspace.PRODUCTION_RUNTIME_MODE
        ):
            return [], []

        issues: list[str] = []
        reason_codes: list[ReasonCode] = []

        if "agent-worker" in profile_services:
            llm_config_path, llm_config_data, llm_config_error = (
                self._load_production_llm_config(config)
            )
            if llm_config_error:
                issues.append(llm_config_error)
                reason_codes.append(ReasonCode.MISSING_CONFIG)
            elif not self._has_live_github_models_credential(
                config,
                llm_config_data,
            ):
                issues.append(
                    "Production runtime requires a non-placeholder GitHub Models "
                    "credential via `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_PAT`, or "
                    f"a non-placeholder `api_key` in `{llm_config_path}`."
                )
                reason_codes.append(ReasonCode.MISSING_SECRET)

        if "github-ops-mcp" in profile_services and is_placeholder_repo_list(
            config.env_values.get(_GITHUB_OPS_ALLOWED_REPOS_ENV_KEY, "")
        ):
            issues.append(
                "Production runtime requires non-placeholder "
                "`GITHUB_OPS_ALLOWED_REPOS` entries for `github-ops-mcp` "
                "(comma-separated `owner/repo` values)."
            )
            reason_codes.append(ReasonCode.MISSING_CONFIG)

        override_issue = self._production_override_issue(config)
        if override_issue:
            issues.append(override_issue)
            reason_codes.append(ReasonCode.PROFILE_MISMATCH)

        return issues, reason_codes

    def _load_production_llm_config(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> tuple[Path | None, dict[str, Any] | None, str | None]:
        raw_path = str(config.env_values.get(_LLM_CONFIG_PATH_ENV_KEY, "")).strip()
        candidates = self._llm_config_candidates(config, raw_path)
        llm_config_path = next(
            (candidate for candidate in candidates if candidate.exists()), None
        )

        if llm_config_path is None:
            if raw_path:
                checked_paths = ", ".join(str(path) for path in candidates)
                return (
                    None,
                    None,
                    "Production runtime requires `LLM_CONFIG_PATH` to resolve to an "
                    f"existing JSON file. Checked: {checked_paths}",
                )
            return (
                None,
                None,
                "Production runtime requires a readable LLM configuration file for "
                "the agent-worker GitHub Models path, but no default config was found.",
            )

        try:
            data = json.loads(llm_config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return (
                llm_config_path,
                None,
                f"Production runtime requires valid JSON in `{llm_config_path}`: {exc}",
            )

        if not isinstance(data, dict):
            return (
                llm_config_path,
                None,
                f"Production runtime requires `{llm_config_path}` to contain a JSON object.",
            )

        return llm_config_path, data, None

    def _llm_config_candidates(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        raw_path: str,
    ) -> tuple[Path, ...]:
        if raw_path:
            return self._resolve_runtime_path_candidates(config, raw_path)

        candidates = [Path("/config/llm.json")]
        for base_dir in (config.factory_dir, config.target_dir, Path.cwd()):
            candidates.append((base_dir / "configs/llm.json").resolve())
            candidates.append((base_dir / "configs/llm.default.json").resolve())

        return tuple(dict.fromkeys(candidates))

    def _resolve_runtime_path_candidates(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        raw_path: str,
    ) -> tuple[Path, ...]:
        expanded = Path(raw_path).expanduser()
        if expanded.is_absolute():
            return (expanded.resolve(),)

        candidates = [
            (config.target_dir / expanded).resolve(),
            (config.factory_dir / expanded).resolve(),
            (Path.cwd() / expanded).resolve(),
        ]
        return tuple(dict.fromkeys(candidates))

    def _extract_api_keys_from_config(self, value: Any) -> tuple[str, ...]:
        collected: list[str] = []

        def _walk(candidate: Any) -> None:
            if isinstance(candidate, dict):
                for key, item in candidate.items():
                    if str(key) == "api_key" and isinstance(item, str):
                        collected.append(item)
                    else:
                        _walk(item)
            elif isinstance(candidate, list):
                for item in candidate:
                    _walk(item)

        _walk(value)
        return tuple(collected)

    def _has_live_github_models_credential(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        llm_config_data: dict[str, Any] | None,
    ) -> bool:
        for env_key in _PRODUCTION_GITHUB_CREDENTIAL_ENV_KEYS:
            if not is_blank_or_placeholder(config.env_values.get(env_key, "")):
                return True

        if llm_config_data is None:
            return False

        return any(
            not is_blank_or_placeholder(candidate)
            for candidate in self._extract_api_keys_from_config(llm_config_data)
        )

    def _production_override_issue(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> str | None:
        raw_path = str(config.env_values.get(_LLM_OVERRIDE_PATH_ENV_KEY, "")).strip()
        default_path = raw_path or "configs/runtime_override.json"
        candidates = self._resolve_runtime_path_candidates(config, default_path)
        override_path = next(
            (candidate for candidate in candidates if candidate.exists()), None
        )
        if override_path is None:
            return None

        return (
            "Production runtime disables dynamic override files via "
            f"`{_LLM_OVERRIDE_PATH_ENV_KEY}`; remove `{override_path}` or switch "
            "to development mode."
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

    def _resolve_factory_data_dir(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> Path:
        data_dir_value = str(config.env_values.get("FACTORY_DATA_DIR", "")).strip()
        if not data_dir_value:
            raise RuntimeError(
                "Supported runtime backup requires `FACTORY_DATA_DIR` to be configured."
            )
        return Path(data_dir_value).expanduser().resolve()

    def _create_backup_bundle_dir(
        self,
        data_root: Path,
        instance_id: str,
        bundle_created_at: str,
    ) -> Path:
        backup_root = data_root / BACKUP_BUNDLES_DIRNAME / instance_id
        backup_root.mkdir(parents=True, exist_ok=True)

        base_name = (
            f"{BACKUP_BUNDLE_PREFIX}"
            f"{bundle_created_at.replace('-', '').replace(':', '')}"
        )
        candidate = backup_root / base_name
        suffix = 2
        while candidate.exists():
            candidate = backup_root / f"{base_name}-{suffix}"
            suffix += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate

    def _load_restore_bundle_manifest(self, bundle_dir: Path) -> dict[str, Any]:
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            raise RuntimeError(
                "Supported runtime restore requires an existing backup bundle "
                f"directory, but `{bundle_dir}` was not found."
            )
        return self._load_json_object(
            bundle_dir / BACKUP_MANIFEST_FILENAME,
            label="backup bundle manifest",
        )

    def _load_json_object(self, path: Path, *, label: str) -> dict[str, Any]:
        if not path.exists():
            raise RuntimeError(
                f"Supported runtime restore requires {label} at `{path}`."
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"Supported runtime restore could not parse {label} at `{path}`: {exc}"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError(
                f"Supported runtime restore requires {label} at `{path}` to contain a JSON object."
            )
        return data

    def _validate_restore_bundle_artifacts(
        self,
        bundle_dir: Path,
        bundle_manifest: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        schema_version = bundle_manifest.get("schema_version")
        if schema_version != 1:
            raise RuntimeError(
                "Supported runtime restore requires backup bundle schema_version `1`, "
                f"but `{schema_version}` was recorded."
            )
        if (
            str(bundle_manifest.get("required_precondition", "")).strip()
            != RuntimeLifecycleState.SUSPENDED.value
        ):
            raise RuntimeError(
                "Supported runtime restore requires a bundle captured from the "
                "bounded `suspended` lifecycle state."
            )
        if (
            str(bundle_manifest.get("runtime_state", "")).strip()
            != RuntimeLifecycleState.SUSPENDED.value
        ):
            raise RuntimeError(
                "Supported runtime restore only supports bundles whose runtime_state "
                "was recorded as `suspended`."
            )
        if str(
            bundle_manifest.get("recovery_classification", "")
        ).strip() != RecoveryClassification.RESUME_SAFE.value or not bool(
            bundle_manifest.get("completed_tool_call_boundary")
        ):
            raise RuntimeError(
                "Supported runtime restore only accepts bundles captured from a "
                "`resume-safe` suspended boundary with `completed_tool_call_boundary=true`."
            )
        if (
            str(bundle_manifest.get("checksums_file", "")).strip()
            != BACKUP_CHECKSUMS_FILENAME
        ):
            raise RuntimeError(
                "Supported runtime restore requires the canonical checksum manifest "
                f"`{BACKUP_CHECKSUMS_FILENAME}`."
            )

        raw_artifacts = bundle_manifest.get("artifacts")
        if not isinstance(raw_artifacts, list) or not raw_artifacts:
            raise RuntimeError(
                "Supported runtime restore requires a non-empty `artifacts` list in the backup bundle manifest."
            )

        checksum_entries = self._load_restore_checksum_entries(
            bundle_dir / BACKUP_CHECKSUMS_FILENAME
        )
        artifact_catalog: dict[str, dict[str, Any]] = {}

        for raw_artifact in raw_artifacts:
            if not isinstance(raw_artifact, dict):
                raise RuntimeError(
                    "Supported runtime restore requires every backup manifest artifact entry to be a JSON object."
                )
            logical_name = str(raw_artifact.get("logical_name", "")).strip()
            relative_path_text = str(
                raw_artifact.get("bundle_relative_path", "")
            ).strip()
            if not logical_name or not relative_path_text:
                raise RuntimeError(
                    "Supported runtime restore requires each backup artifact entry "
                    "to include logical_name and bundle_relative_path."
                )
            if logical_name in artifact_catalog:
                raise RuntimeError(
                    "Supported runtime restore requires unique backup artifact "
                    f"logical names, but `{logical_name}` was duplicated."
                )

            relative_path = Path(relative_path_text)
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise RuntimeError(
                    "Supported runtime restore rejects backup artifact paths that "
                    f"escape the bundle root: `{relative_path_text}`."
                )

            artifact_path = (bundle_dir / relative_path).resolve()
            try:
                artifact_path.relative_to(bundle_dir)
            except ValueError as exc:
                raise RuntimeError(
                    "Supported runtime restore rejects backup artifact paths that "
                    f"escape the bundle root: `{relative_path_text}`."
                ) from exc
            if not artifact_path.exists() or not artifact_path.is_file():
                raise RuntimeError(
                    "Supported runtime restore requires bundled artifact "
                    f"`{logical_name}` at `{artifact_path}`."
                )

            checksum_key = relative_path.as_posix()
            expected_checksum = checksum_entries.get(checksum_key, "")
            if not expected_checksum:
                raise RuntimeError(
                    "Supported runtime restore requires a checksum entry for backup "
                    f"artifact `{checksum_key}`."
                )
            actual_checksum = self._sha256_file(artifact_path)
            if actual_checksum != expected_checksum:
                raise RuntimeError(
                    "Supported runtime restore detected a checksum mismatch for "
                    f"`{checksum_key}`. Expected `{expected_checksum}` but found `{actual_checksum}`."
                )

            manifest_checksum = str(raw_artifact.get("sha256", "")).strip()
            if manifest_checksum and manifest_checksum != actual_checksum:
                raise RuntimeError(
                    "Supported runtime restore detected a bundle-manifest checksum "
                    f"mismatch for `{checksum_key}`."
                )
            size_bytes = raw_artifact.get("size_bytes")
            if size_bytes is not None:
                expected_size_bytes = self._coerce_restore_int_value(
                    size_bytes,
                    label=f"`size_bytes` value for backup artifact `{checksum_key}`",
                )
                if expected_size_bytes != artifact_path.stat().st_size:
                    raise RuntimeError(
                        "Supported runtime restore detected a size mismatch for backup "
                        f"artifact `{checksum_key}`."
                    )

            artifact_catalog[logical_name] = {
                "path": artifact_path,
                "relative_path": checksum_key,
            }

        missing_artifacts = sorted(_RESTORE_REQUIRED_ARTIFACTS - set(artifact_catalog))
        if missing_artifacts:
            raise RuntimeError(
                "Supported runtime restore requires the canonical backup bundle "
                "artifacts, but these logical names were missing: "
                + ", ".join(missing_artifacts)
            )

        return artifact_catalog

    def _load_restore_checksum_entries(
        self,
        checksums_path: Path,
    ) -> dict[str, str]:
        if not checksums_path.exists() or not checksums_path.is_file():
            raise RuntimeError(
                "Supported runtime restore requires the canonical checksum file at "
                f"`{checksums_path}`."
            )

        entries: dict[str, str] = {}
        for raw_line in checksums_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = raw_line.split("  ", 1)
            if len(parts) != 2:
                raise RuntimeError(
                    "Supported runtime restore requires checksum lines in the form "
                    "`<sha256>  <relative-path>`."
                )
            checksum = parts[0].strip().lower()
            relative_path = parts[1].strip()
            if not re.fullmatch(r"[0-9a-f]{64}", checksum):
                raise RuntimeError(
                    "Supported runtime restore requires SHA-256 checksum entries, "
                    f"but `{parts[0]}` was invalid."
                )
            if not relative_path:
                raise RuntimeError(
                    "Supported runtime restore requires every checksum entry to record a relative path."
                )
            entries[relative_path] = checksum
        if not entries:
            raise RuntimeError(
                "Supported runtime restore requires a non-empty checksum file in the backup bundle."
            )
        return entries

    def _coerce_restore_int_value(self, value: Any, *, label: str) -> int:
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Supported runtime restore detected an invalid {label}: `{value}`."
            ) from exc

    def _build_restore_config(
        self,
        repo_root: Path,
        bundled_env_values: dict[str, str],
        bundled_runtime_manifest: dict[str, Any],
    ) -> factory_workspace.WorkspaceRuntimeConfig:
        target_dir = (
            Path(str(bundled_env_values.get("TARGET_WORKSPACE_PATH", "")).strip())
            .expanduser()
            .resolve()
        )
        if not str(target_dir).strip() or str(target_dir) == ".":
            raise RuntimeError(
                "Supported runtime restore requires `TARGET_WORKSPACE_PATH` in the bundled `.factory.env`."
            )

        ports: dict[str, int] = {}
        for key in factory_workspace.PORT_LAYOUT:
            raw_value = str(bundled_env_values.get(key, "")).strip()
            if not raw_value:
                raise RuntimeError(
                    "Supported runtime restore requires the bundled `.factory.env` "
                    f"to define `{key}`."
                )
            try:
                ports[key] = int(raw_value)
            except ValueError as exc:
                raise RuntimeError(
                    "Supported runtime restore requires integer port values in the "
                    f"bundled `.factory.env`, but `{key}={raw_value}` was invalid."
                ) from exc

        raw_port_index = str(bundled_env_values.get("FACTORY_PORT_INDEX", "")).strip()
        try:
            port_index = int(raw_port_index)
        except ValueError as exc:
            raise RuntimeError(
                "Supported runtime restore requires `FACTORY_PORT_INDEX` in the bundled `.factory.env`."
            ) from exc

        workspace_file = (
            str(
                bundled_runtime_manifest.get(
                    "workspace_file",
                    self._default_workspace_file,
                )
            ).strip()
            or self._default_workspace_file
        )

        normalized_env_values = dict(bundled_env_values)
        normalized_env_values.update(
            {
                "TARGET_WORKSPACE_PATH": str(target_dir),
                "FACTORY_DIR": str(repo_root),
                "FACTORY_PORT_INDEX": str(port_index),
                factory_workspace.RUNTIME_MODE_ENV_KEY: factory_workspace.normalize_runtime_mode(
                    bundled_env_values.get(factory_workspace.RUNTIME_MODE_ENV_KEY, "")
                ),
                **{key: str(value) for key, value in ports.items()},
            }
        )

        shared_service_mode = factory_workspace.normalize_shared_service_mode(
            normalized_env_values.get(factory_workspace.SHARED_SERVICE_MODE_ENV_KEY, "")
        )
        shared_service_urls = {
            service_name: normalized_env_values.get(env_key, "").strip()
            for service_name, env_key in factory_workspace.SHARED_SERVICE_URL_ENV_KEYS.items()
            if normalized_env_values.get(env_key, "").strip()
        }

        return factory_workspace.WorkspaceRuntimeConfig(
            target_dir=target_dir,
            factory_dir=repo_root,
            workspace_file=workspace_file,
            workspace_file_path=(target_dir / workspace_file).resolve(),
            runtime_manifest_path=(
                target_dir
                / factory_workspace.TMP_SUBPATH
                / factory_workspace.RUNTIME_MANIFEST_FILENAME
            ).resolve(),
            project_workspace_id=str(
                normalized_env_values.get("PROJECT_WORKSPACE_ID", "")
            ).strip(),
            factory_instance_id=str(
                normalized_env_values.get("FACTORY_INSTANCE_ID", "")
            ).strip(),
            compose_project_name=str(
                normalized_env_values.get("COMPOSE_PROJECT_NAME", "")
            ).strip(),
            port_index=port_index,
            env_values=normalized_env_values,
            ports=ports,
            runtime_mode=factory_workspace.normalize_runtime_mode(
                normalized_env_values.get(factory_workspace.RUNTIME_MODE_ENV_KEY, "")
            ),
            shared_service_mode=shared_service_mode,
            shared_service_urls=shared_service_urls,
            mcp_server_urls=factory_workspace.build_mcp_server_urls(ports),
            workspace_settings=factory_workspace.build_effective_workspace_settings(
                repo_root,
                ports,
            ),
        )

    def _validate_restore_bundle_identity(
        self,
        *,
        repo_root: Path,
        config: factory_workspace.WorkspaceRuntimeConfig,
        bundle_manifest: dict[str, Any],
        bundled_env_values: dict[str, str],
        bundled_runtime_manifest: dict[str, Any],
        bundled_runtime_snapshot: dict[str, Any],
        bundled_registry_snapshot: dict[str, Any],
    ) -> None:
        expected_factory_dir = (
            config.target_dir / factory_workspace.FACTORY_DIRNAME
        ).resolve()
        if repo_root != expected_factory_dir:
            raise RuntimeError(
                "Supported runtime restore must run against the canonical installed "
                f"workspace root `{expected_factory_dir}`, but received `{repo_root}`."
            )

        workspace_record = bundled_registry_snapshot.get("workspace_record")
        if not isinstance(workspace_record, dict):
            raise RuntimeError(
                "Supported runtime restore requires the bundled workspace registry "
                "snapshot to include `workspace_record`."
            )

        self._validate_restore_identity_group(
            "workspace_id",
            config.project_workspace_id,
            (
                (
                    "bundled .factory.env",
                    bundled_env_values.get("PROJECT_WORKSPACE_ID", ""),
                ),
                ("backup bundle manifest", bundle_manifest.get("workspace_id", "")),
                (
                    "bundled runtime manifest",
                    bundled_runtime_manifest.get("project_workspace_id", ""),
                ),
                (
                    "bundled runtime snapshot",
                    bundled_runtime_snapshot.get("workspace_id", ""),
                ),
                (
                    "bundled workspace registry",
                    workspace_record.get("project_workspace_id", ""),
                ),
            ),
        )
        self._validate_restore_identity_group(
            "instance_id",
            config.factory_instance_id,
            (
                (
                    "bundled .factory.env",
                    bundled_env_values.get("FACTORY_INSTANCE_ID", ""),
                ),
                ("backup bundle manifest", bundle_manifest.get("instance_id", "")),
                (
                    "bundled runtime manifest",
                    bundled_runtime_manifest.get("factory_instance_id", ""),
                ),
                (
                    "bundled runtime snapshot",
                    bundled_runtime_snapshot.get("instance_id", ""),
                ),
                (
                    "bundled workspace registry",
                    workspace_record.get("factory_instance_id", ""),
                ),
            ),
        )
        self._validate_restore_identity_group(
            "compose_project_name",
            config.compose_project_name,
            (
                (
                    "bundled .factory.env",
                    bundled_env_values.get("COMPOSE_PROJECT_NAME", ""),
                ),
                (
                    "backup bundle manifest",
                    bundle_manifest.get("compose_project_name", ""),
                ),
                (
                    "bundled runtime manifest",
                    bundled_runtime_manifest.get("compose_project_name", ""),
                ),
                (
                    "bundled runtime snapshot",
                    bundled_runtime_snapshot.get("compose_project_name", ""),
                ),
                (
                    "bundled workspace registry",
                    workspace_record.get("compose_project_name", ""),
                ),
            ),
        )
        self._validate_restore_identity_group(
            "target_workspace_path",
            str(config.target_dir),
            (
                (
                    "bundled .factory.env",
                    bundled_env_values.get("TARGET_WORKSPACE_PATH", ""),
                ),
                ("backup bundle manifest", bundle_manifest.get("target_dir", "")),
                (
                    "bundled runtime manifest",
                    bundled_runtime_manifest.get("target_workspace_path", ""),
                ),
                (
                    "bundled runtime snapshot",
                    bundled_runtime_snapshot.get("target_dir", ""),
                ),
                (
                    "bundled workspace registry",
                    workspace_record.get("target_workspace_path", ""),
                ),
            ),
            path_like=True,
        )
        self._validate_restore_identity_group(
            "factory_dir",
            str(repo_root),
            (
                ("bundled .factory.env", bundled_env_values.get("FACTORY_DIR", "")),
                ("backup bundle manifest", bundle_manifest.get("factory_dir", "")),
                (
                    "bundled runtime manifest",
                    bundled_runtime_manifest.get("factory_dir", ""),
                ),
                (
                    "bundled runtime snapshot",
                    bundled_runtime_snapshot.get("factory_dir", ""),
                ),
                ("bundled workspace registry", workspace_record.get("factory_dir", "")),
            ),
            path_like=True,
        )

        self._validate_restore_port_metadata(
            config,
            bundled_runtime_manifest,
            workspace_record,
        )

    def _validate_restore_identity_group(
        self,
        label: str,
        expected_value: Any,
        candidates: Sequence[tuple[str, Any]],
        *,
        path_like: bool = False,
    ) -> None:
        normalized_expected = self._normalize_restore_identity_value(
            expected_value,
            path_like=path_like,
        )
        if not normalized_expected:
            raise RuntimeError(
                f"Supported runtime restore requires a non-empty `{label}` for the current target."
            )

        for source_name, candidate_value in candidates:
            normalized_candidate = self._normalize_restore_identity_value(
                candidate_value,
                path_like=path_like,
            )
            if normalized_candidate != normalized_expected:
                raise RuntimeError(
                    "Supported runtime restore requires a consistent "
                    f"`{label}` across the backup bundle and current target. "
                    f"Expected `{normalized_expected}` but {source_name} recorded `{normalized_candidate}`."
                )

    def _normalize_restore_identity_value(
        self,
        value: Any,
        *,
        path_like: bool,
    ) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if not path_like:
            return text
        return str(Path(text).expanduser().resolve())

    def _validate_restore_port_metadata(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
        bundled_runtime_manifest: dict[str, Any],
        workspace_record: dict[str, Any],
    ) -> None:
        for source_name, raw_ports in (
            ("bundled runtime manifest", bundled_runtime_manifest.get("ports", {})),
            ("bundled workspace registry", workspace_record.get("ports", {})),
        ):
            normalized_ports: dict[str, int] = {}
            if isinstance(raw_ports, dict):
                for key, value in raw_ports.items():
                    if key not in factory_workspace.PORT_LAYOUT:
                        continue
                    normalized_ports[key] = self._coerce_restore_int_value(
                        value,
                        label=f"port value for `{key}` in {source_name}",
                    )
            if normalized_ports and normalized_ports != config.ports:
                raise RuntimeError(
                    "Supported runtime restore requires the backed-up runtime port "
                    f"block to stay consistent, but {source_name} disagreed with the bundled `.factory.env`."
                )

        expected_port_index = config.port_index
        runtime_manifest_port_index = bundled_runtime_manifest.get("port_index")
        if (
            runtime_manifest_port_index is not None
            and self._coerce_restore_int_value(
                runtime_manifest_port_index,
                label="`port_index` value in bundled runtime manifest",
            )
            != expected_port_index
        ):
            raise RuntimeError(
                "Supported runtime restore requires the backed-up `port_index` to "
                "match the bundled `.factory.env`."
            )
        registry_port_index = workspace_record.get("port_index")
        if (
            registry_port_index is not None
            and self._coerce_restore_int_value(
                registry_port_index,
                label="`port_index` value in bundled workspace registry",
            )
            != expected_port_index
        ):
            raise RuntimeError(
                "Supported runtime restore requires the backed-up registry `port_index` to "
                "match the bundled `.factory.env`."
            )

    def _validate_restore_port_safety(
        self,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> None:
        factory_workspace.assert_ports_do_not_conflict(
            config.ports,
            registry_path=self._registry_path,
            exclude_instance_id=config.factory_instance_id,
        )
        if not factory_workspace.ports_available(config.ports):
            raise RuntimeError(
                "Supported runtime restore requires the backed-up port block to be "
                "available before metadata is rewritten. Resolve the current port "
                "collision and retry the restore."
            )

    def _validate_restore_runtime_stopped(self, compose_project_name: str) -> None:
        if not compose_project_name or not self._docker_available():
            return
        try:
            inventory = self._collect_service_inventory(compose_project_name)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Supported runtime restore requires proving the compose project is "
                "fully stopped before mutating runtime state, but service "
                f"inventory for compose project `{compose_project_name}` could not "
                "be collected. Ensure Docker is reachable, verify the compose "
                "project state manually, stop any running services, and retry the "
                f"restore. Inventory error: {exc}"
            ) from exc

        running_services = [
            service_name
            for service_name, service_data in inventory.items()
            if "up" in str(service_data.get("status", "")).lower()
        ]
        if running_services:
            raise RuntimeError(
                "Supported runtime restore requires the compose project to be fully "
                "stopped before mutating runtime state. Running services: "
                + ", ".join(sorted(running_services))
            )

    def _restore_bundle_file(self, source_path: Path, destination_path: Path) -> None:
        temporary_path = destination_path.with_name(
            destination_path.name + ".restore-tmp"
        )
        for attempt in range(2):
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            if temporary_path.exists():
                temporary_path.unlink()
            try:
                shutil.copyfile(source_path, temporary_path)
                temporary_path.replace(destination_path)
                return
            except FileNotFoundError as exc:
                if temporary_path.exists():
                    temporary_path.unlink()
                if attempt == 0 and str(exc.filename or "").strip() == str(
                    temporary_path
                ):
                    continue
                raise
            except Exception:
                if temporary_path.exists():
                    temporary_path.unlink()
                raise

    def _resolve_restore_boundary_timestamp(
        self,
        bundle_manifest: dict[str, Any],
        bundled_runtime_snapshot: dict[str, Any],
        bundled_registry_snapshot: dict[str, Any],
    ) -> str | None:
        recovery = bundled_runtime_snapshot.get("recovery")
        if isinstance(recovery, dict):
            boundary_at = str(recovery.get("last_completed_tool_call_at", "")).strip()
            if boundary_at:
                return boundary_at

        workspace_record = bundled_registry_snapshot.get("workspace_record")
        if isinstance(workspace_record, dict):
            boundary_at = str(
                workspace_record.get("last_completed_tool_call_boundary_at", "")
            ).strip()
            if boundary_at:
                return boundary_at

        bundle_created_at = str(bundle_manifest.get("bundle_created_at", "")).strip()
        return bundle_created_at or None

    def _build_backup_registry_snapshot(
        self,
        snapshot: RuntimeSnapshot,
        config: factory_workspace.WorkspaceRuntimeConfig,
    ) -> dict[str, Any]:
        matched_instance_id, existing_record, registry = (
            self._load_runtime_registry_entry(
                snapshot.instance_id,
                snapshot.target_dir,
            )
        )
        if existing_record is None:
            workspace_record = factory_workspace.build_registry_record_from_manifest(
                factory_workspace.build_runtime_manifest(config),
                runtime_state=snapshot.persisted_runtime_state,
            )
            record_source = "manifest-fallback"
        else:
            workspace_record = dict(existing_record)
            record_source = "registry"

        registry_path = (
            self._registry_path.resolve()
            if self._registry_path is not None
            else factory_workspace.default_registry_path()
        )
        return {
            "schema_version": 1,
            "captured_at": factory_workspace.utc_now_iso(),
            "registry_path": str(registry_path),
            "active_workspace": str(registry.get("active_workspace", "")),
            "workspace_record_source": record_source,
            "workspace_record_instance_id": matched_instance_id or snapshot.instance_id,
            "workspace_record": workspace_record,
        }

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

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
                    if instance_dir.exists():
                        print(
                            "⚠️ Could not fully erase data directory "
                            f"{instance_dir}; stale bind-mounted contents may "
                            "remain until the host regains write access."
                        )
                    else:
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
            if not is_blank_or_placeholder(config.env_values.get(config_key, "")):
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

    def _normalize_supported_runtime_state(
        self,
        persisted_runtime_state: str,
    ) -> str:
        return persisted_runtime_state.strip()

    def _infer_lifecycle_state(
        self,
        *,
        persisted_runtime_state: str,
        services: dict[str, ServiceRuntimeRecord],
        docker_available: bool,
        installed: bool,
    ) -> RuntimeLifecycleState:
        persisted_degraded = persisted_runtime_state in {"failed", "degraded"}
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
        if not docker_available:
            if persisted_degraded:
                return RuntimeLifecycleState.DEGRADED
            return (
                RuntimeLifecycleState.RUNNING
                if persisted_runtime_state == "running"
                else RuntimeLifecycleState.STOPPED
            )
        if not services:
            return (
                RuntimeLifecycleState.DEGRADED
                if persisted_degraded
                else RuntimeLifecycleState.STOPPED
            )

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
            return (
                RuntimeLifecycleState.DEGRADED
                if persisted_degraded
                else RuntimeLifecycleState.STOPPED
            )
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
        return (
            RuntimeLifecycleState.DEGRADED
            if persisted_degraded
            else RuntimeLifecycleState.STOPPED
        )

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
