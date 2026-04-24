"""Phase-1 MCP runtime-manager package.

Exports the authoritative contract surface introduced for the runtime-manager
rollout without changing the current operator-facing lifecycle CLI surface.
"""

from factory_runtime.mcp_runtime.catalog import DEFAULT_RUNTIME_CATALOG, build_catalog
from factory_runtime.mcp_runtime.manager import MCPRuntimeManager
from factory_runtime.mcp_runtime.models import (
    LeaseKind,
    LeaseMetadata,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RecommendedAction,
    RecoveryClassification,
    RecoveryMetadata,
    RepairPolicyClass,
    RepairResult,
    RepairStep,
    RuntimeActionTrigger,
    RuntimeCatalog,
    RuntimeLifecycleState,
    RuntimeMode,
    RuntimeProfile,
    RuntimeProfileName,
    RuntimeSnapshot,
    SelectedProfiles,
    SelectionMetadata,
    ServiceCatalogEntry,
    ServiceInstanceStatus,
    ServiceKind,
    ServiceReadinessSemantics,
    ServiceRuntimeRecord,
    ServiceScope,
)

__all__ = [
    "DEFAULT_RUNTIME_CATALOG",
    "RecoveryClassification",
    "RecoveryMetadata",
    "LeaseKind",
    "LeaseMetadata",
    "MCPRuntimeManager",
    "ReadinessResult",
    "ReadinessStatus",
    "ReasonCode",
    "RecommendedAction",
    "RepairPolicyClass",
    "RepairResult",
    "RepairStep",
    "RuntimeCatalog",
    "RuntimeActionTrigger",
    "RuntimeLifecycleState",
    "RuntimeMode",
    "RuntimeProfile",
    "RuntimeProfileName",
    "RuntimeSnapshot",
    "SelectedProfiles",
    "SelectionMetadata",
    "ServiceCatalogEntry",
    "ServiceInstanceStatus",
    "ServiceKind",
    "ServiceReadinessSemantics",
    "ServiceRuntimeRecord",
    "ServiceScope",
    "build_catalog",
]
