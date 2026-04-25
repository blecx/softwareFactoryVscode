"""Typed MCP runtime-manager contract models.

These models establish the phase-1 package boundary for the authoritative MCP
runtime manager described by `ADR-014`, while respecting the document-authority
hierarchy from `ADR-013` and the existing `installed`/`active` meanings from
`ADR-009`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable


class RuntimeProfileName(StrEnum):
    """Named runtime profiles for static service selection."""

    WORKSPACE_DEFAULT = "workspace-default"
    WORKSPACE_PRODUCTION = "workspace-production"
    HARNESS_DEFAULT = "harness-default"


class RuntimeMode(StrEnum):
    """Operator-visible runtime mode for manager-backed readiness."""

    DEVELOPMENT = "development"
    PRODUCTION = "production"


class ServiceKind(StrEnum):
    """Logical kind for one catalog entry."""

    MCP = "mcp"
    SUPPORT_HTTP = "support-http"
    WORKER = "worker"


class ServiceScope(StrEnum):
    """Architectural scope for one runtime service."""

    WORKSPACE_SCOPED = "workspace-scoped"
    SHARED_CAPABLE = "shared-capable"


class RepairPolicyClass(StrEnum):
    """Repair-policy class from the manager catalog."""

    CORE = "core"
    OPTIONAL = "optional"


class RuntimeLifecycleState(StrEnum):
    """ADR-014 lifecycle layer A states.

    This enum deliberately excludes `installed` and `active`. Those remain
    separate architectural facts per `ADR-009`.

    `SUSPENDED` is a supported, bounded lifecycle state once the authoritative
    runtime manager enters it explicitly. Operator-facing surfaces must also
    publish the recovery metadata needed to classify resume as safe, unsafe, or
    manual.
    """

    STARTING = "starting"
    RUNNING = "running"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    REPAIRING = "repairing"
    DEGRADED = "degraded"
    RUNTIME_DELETED = "runtime-deleted"


class ReadinessStatus(StrEnum):
    """Normalized readiness statuses used by the manager contract."""

    READY = "ready"
    NEEDS_RAMP_UP = "needs-ramp-up"
    CONFIG_DRIFT = "config-drift"
    DEGRADED = "degraded"
    DOCKER_UNAVAILABLE = "docker-unavailable"
    DOCKER_ERROR = "docker-error"
    ERROR = "error"


class RecommendedAction(StrEnum):
    """Normalized operator/action hints for readiness outcomes."""

    NONE = "none"
    START = "start"
    RESUME = "resume"
    INSPECT = "inspect"
    REBOOTSTRAP = "re-bootstrap"
    INSPECT_SHARED_TOPOLOGY = "inspect-shared-topology"
    INSTALL_DOCKER = "install-docker"
    INSPECT_DOCKER = "inspect-docker"
    INSPECT_REGISTRY = "inspect-registry"
    REPAIR = "repair"


class ReasonCode(StrEnum):
    """Normalized reason-code vocabulary for runtime status and repair."""

    MISSING_CONFIG = "missing-config"
    MISSING_SECRET = "missing-secret"
    MISSING_MOUNT = "missing-mount"
    DEPENDENCY_UNHEALTHY = "dependency-unhealthy"
    IDENTITY_MISMATCH = "identity-mismatch"
    ENDPOINT_UNREACHABLE = "endpoint-unreachable"
    MCP_INITIALIZE_FAILED = "mcp-initialize-failed"
    PROFILE_MISMATCH = "profile-mismatch"
    DOCKER_UNAVAILABLE = "docker-unavailable"
    DOCKER_INSPECTION_FAILED = "docker-inspection-failed"
    WORKSPACE_URL_DRIFT = "workspace-url-drift"
    MANIFEST_SERVER_URL_DRIFT = "manifest-server-url-drift"
    MANIFEST_HEALTH_URL_DRIFT = "manifest-health-url-drift"
    SHARED_SERVICE_DISCOVERY_MISSING = "shared-service-discovery-missing"
    SHARED_MODE_TENANT_ENFORCEMENT_MISSING = "shared-mode-tenant-enforcement-missing"
    SHARED_MODE_WORKSPACE_DUPLICATE = "shared-mode-workspace-duplicate"
    SERVICE_MISSING = "service-missing"
    SERVICE_NOT_RUNNING = "service-not-running"
    SERVICE_UNHEALTHY = "service-unhealthy"
    SERVICE_PORT_MISMATCH = "service-port-mismatch"
    NO_RUNNING_SERVICES = "no-running-services"
    REGISTRY_RECORD_MISSING = "registry-record-missing"
    MISSING_RUNTIME_METADATA = "missing-runtime-metadata"
    TERMINAL_RUNTIME_FAILURE = "terminal-runtime-failure"
    REPAIR_NOT_IMPLEMENTED = "repair-not-implemented"
    REPAIR_REPROBE = "repair-reprobe"
    REPAIR_RESTART = "repair-restart"
    REPAIR_RECREATE = "repair-recreate"
    REPAIR_DEPENDENCY = "repair-dependency"
    REPAIR_RECONCILE_METADATA = "repair-reconcile-metadata"
    REPAIR_CIRCUIT_BREAKER = "repair-circuit-breaker"
    BACKUP_REQUESTED = "backup-requested"
    RESTORE_REQUESTED = "restore-requested"
    SUSPEND_REQUESTED = "suspend-requested"
    SUSPEND_REQUIRES_READY_RUNTIME = "suspend-requires-ready-runtime"
    RESUME_REQUESTED = "resume-requested"
    RESUME_REPAIR_ATTEMPTED = "resume-repair-attempted"
    HOST_DOCKER_UNAVAILABLE = "host-docker-unavailable"
    HOST_NETWORK_UNAVAILABLE = "host-network-unavailable"
    HOST_DISK_EXHAUSTED = "host-disk-exhausted"
    UNEXPECTED_ERROR = "unexpected-error"


class ServiceInstanceStatus(StrEnum):
    """Per-service runtime status inside the canonical snapshot."""

    RUNNING = "running"
    DEGRADED = "degraded"
    MISSING = "missing"
    STOPPED = "stopped"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class LeaseKind(StrEnum):
    """Lease categories tracked in selection metadata."""

    ACTIVITY = "activity"
    EXECUTION = "execution"


class RepairStep(StrEnum):
    """Bounded repair ladder steps."""

    REPROBE = "reprobe"
    RESTART_SERVICE = "restart-service"
    RECREATE_SERVICE = "recreate-service"
    REPAIR_DEPENDENCY = "repair-dependency"
    RECONCILE_METADATA = "reconcile-metadata"
    SURFACE_TERMINAL_FAILURE = "surface-terminal-failure"


class RuntimeActionTrigger(StrEnum):
    """Normalized trigger vocabulary for manager-owned runtime actions."""

    BACKUP = "backup"
    CLEANUP = "cleanup"
    DELETE_RUNTIME = "delete-runtime"
    REPAIR = "repair"
    RESTORE = "restore"
    SUSPEND = "suspend"
    RESUME = "resume"


class RecoveryClassification(StrEnum):
    """Minimal recovery/resume classification at completed tool-call boundaries."""

    RESUME_SAFE = "resume-safe"
    RESUME_UNSAFE = "resume-unsafe"
    MANUAL_RECOVERY_REQUIRED = "manual-recovery-required"


@dataclass(frozen=True, slots=True)
class LeaseMetadata:
    """Lease metadata for operator activity or execution ownership."""

    kind: LeaseKind
    present: bool = False
    holder: str = ""
    renewed_at: str | None = None
    expires_at: str | None = None


@dataclass(frozen=True, slots=True)
class ServiceReadinessSemantics:
    """Readiness rules attached to one catalog entry."""

    health_path: str = ""
    requires_container_healthy: bool = True
    requires_endpoint_reachability: bool = True
    requires_mcp_initialize: bool = False
    allow_http_error: bool = False


@dataclass(frozen=True, slots=True)
class ServiceCatalogEntry:
    """Machine-readable service catalog entry."""

    name: str
    runtime_identity: str
    service_kind: ServiceKind
    scope: ServiceScope
    profiles: tuple[RuntimeProfileName, ...]
    dependencies: tuple[str, ...] = ()
    required_mounts: tuple[str, ...] = ()
    required_config_keys: tuple[str, ...] = ()
    readiness: ServiceReadinessSemantics = field(
        default_factory=ServiceReadinessSemantics
    )
    repair_policy_class: RepairPolicyClass = RepairPolicyClass.CORE
    workspace_server_name: str | None = None
    port_env_key: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    """Static profile definition for one class of runtime use."""

    name: RuntimeProfileName
    description: str
    required_services: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SelectedProfiles:
    """Resolved selected-profile set with the required service closure."""

    names: tuple[RuntimeProfileName, ...]
    required_services: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuntimeCatalog:
    """Machine-readable runtime service catalog plus profile definitions."""

    services: dict[str, ServiceCatalogEntry]
    profiles: dict[RuntimeProfileName, RuntimeProfile]

    def normalize_profile_names(
        self,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> tuple[RuntimeProfileName, ...]:
        if selected_profiles is None:
            return (RuntimeProfileName.WORKSPACE_DEFAULT,)

        normalized: list[RuntimeProfileName] = []
        for profile in selected_profiles:
            candidate = (
                profile
                if isinstance(profile, RuntimeProfileName)
                else RuntimeProfileName(str(profile).strip())
            )
            if candidate not in self.profiles:
                raise ValueError(f"Unknown runtime profile: {candidate}")
            if candidate not in normalized:
                normalized.append(candidate)
        return tuple(normalized) or (RuntimeProfileName.WORKSPACE_DEFAULT,)

    def select_profiles(
        self,
        selected_profiles: Iterable[RuntimeProfileName | str] | None = None,
    ) -> SelectedProfiles:
        names = self.normalize_profile_names(selected_profiles)
        required_services: list[str] = []
        for name in names:
            profile = self.profiles[name]
            for service_name in profile.required_services:
                if service_name not in required_services:
                    required_services.append(service_name)
        return SelectedProfiles(names=names, required_services=tuple(required_services))


@dataclass(frozen=True, slots=True)
class SelectionMetadata:
    """Layer-B selection metadata from the runtime snapshot."""

    installed: bool
    active: bool
    profiles: SelectedProfiles
    activity_lease: LeaseMetadata | None = None
    execution_lease: LeaseMetadata | None = None


@dataclass(frozen=True, slots=True)
class ServiceRuntimeRecord:
    """Per-service status record inside the runtime snapshot."""

    service_name: str
    runtime_identity: str
    service_kind: ServiceKind
    scope: ServiceScope
    topology_mode: str
    workspace_owned: bool
    status: ServiceInstanceStatus
    docker_status: str = ""
    published_ports: tuple[int, ...] = ()
    expected_port: int | None = None
    workspace_server_name: str | None = None
    discovery_url: str = ""
    probe_url: str = ""
    reason_codes: tuple[ReasonCode, ...] = ()
    details: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadinessResult:
    """Canonical readiness outcome for one selected profile set."""

    status: ReadinessStatus
    recommended_action: RecommendedAction
    ready: bool
    reason_codes: tuple[ReasonCode, ...] = ()
    issues: tuple[str, ...] = ()
    blocking_services: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecoveryMetadata:
    """Minimal recovery metadata surfaced through the canonical snapshot."""

    classification: RecoveryClassification
    completed_tool_call_boundary: bool
    last_completed_tool_call_at: str | None = None
    last_trigger: RuntimeActionTrigger | None = None
    last_trigger_at: str | None = None
    last_reason_codes: tuple[ReasonCode, ...] = ()
    repair_failure_count: int = 0
    circuit_breaker_tripped: bool = False
    circuit_breaker_tripped_at: str | None = None


@dataclass(frozen=True, slots=True)
class RepairResult:
    """Repair entrypoint result for the manager contract."""

    attempted: bool
    success: bool
    attempted_steps: tuple[RepairStep, ...] = ()
    reason_codes: tuple[ReasonCode, ...] = ()
    details: tuple[str, ...] = ()
    final_state: RuntimeLifecycleState | None = None


@dataclass(frozen=True, slots=True)
class RuntimeSnapshot:
    """Canonical runtime snapshot for one workspace runtime identity."""

    workspace_id: str
    instance_id: str
    target_dir: Path
    factory_dir: Path
    compose_project_name: str
    lifecycle_state: RuntimeLifecycleState
    selection: SelectionMetadata
    persisted_runtime_state: str
    runtime_mode: RuntimeMode = RuntimeMode.DEVELOPMENT
    last_transition_at: str | None = None
    last_transition_reason_codes: tuple[ReasonCode, ...] = ()
    shared_mode: str = ""
    shared_mode_status: str = ""
    runtime_topology: dict[str, Any] = field(default_factory=dict)
    shared_mode_diagnostics: dict[str, Any] = field(default_factory=dict)
    workspace_urls: dict[str, str] = field(default_factory=dict)
    manifest_server_urls: dict[str, str] = field(default_factory=dict)
    manifest_health_urls: dict[str, str] = field(default_factory=dict)
    expected_workspace_urls: dict[str, str] = field(default_factory=dict)
    expected_health_urls: dict[str, str] = field(default_factory=dict)
    expected_service_ports: dict[str, int] = field(default_factory=dict)
    services: dict[str, ServiceRuntimeRecord] = field(default_factory=dict)
    catalog: RuntimeCatalog | None = None
    readiness: ReadinessResult | None = None
    recovery: RecoveryMetadata | None = None
    docker_available: bool = True
    inventory_error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return serialize_contract_value(self)


def serialize_contract_value(value: Any) -> Any:
    """Convert runtime-manager contract values into JSON-friendly structures."""

    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {
            field_name: serialize_contract_value(getattr(value, field_name))
            for field_name in value.__dataclass_fields__
        }
    if isinstance(value, dict):
        return {str(key): serialize_contract_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_contract_value(item) for item in value]
    return value
