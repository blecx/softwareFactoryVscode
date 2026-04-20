"""Canonical MCP runtime service catalog and static profile definitions.

Per `ADR-013`, this module sequences implementation details within the accepted
runtime terminology from `ADR-014`; it does not redefine architecture terms.
"""

from __future__ import annotations

from factory_runtime.mcp_runtime.models import (
    RepairPolicyClass,
    RuntimeCatalog,
    RuntimeProfile,
    RuntimeProfileName,
    ServiceCatalogEntry,
    ServiceKind,
    ServiceReadinessSemantics,
    ServiceScope,
)


def _mcp_semantics(*, health_path: str = "/mcp") -> ServiceReadinessSemantics:
    return ServiceReadinessSemantics(
        health_path=health_path,
        requires_container_healthy=True,
        requires_endpoint_reachability=True,
        requires_mcp_initialize=True,
        allow_http_error=True,
    )


def _http_semantics(
    health_path: str,
    *,
    allow_http_error: bool = False,
) -> ServiceReadinessSemantics:
    return ServiceReadinessSemantics(
        health_path=health_path,
        requires_container_healthy=True,
        requires_endpoint_reachability=True,
        requires_mcp_initialize=False,
        allow_http_error=allow_http_error,
    )


def _worker_semantics() -> ServiceReadinessSemantics:
    return ServiceReadinessSemantics(
        health_path="",
        requires_container_healthy=True,
        requires_endpoint_reachability=False,
        requires_mcp_initialize=False,
        allow_http_error=False,
    )


def build_catalog() -> RuntimeCatalog:
    """Build the authoritative machine-readable service catalog."""

    services = {
        "mock-llm-gateway": ServiceCatalogEntry(
            name="mock-llm-gateway",
            runtime_identity="mock-llm-gateway",
            service_kind=ServiceKind.SUPPORT_HTTP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_http_semantics("/admin/mocks"),
            repair_policy_class=RepairPolicyClass.CORE,
            port_env_key="PORT_TUI",
        ),
        "mcp-memory": ServiceCatalogEntry(
            name="mcp-memory",
            runtime_identity="mcp-memory",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.SHARED_CAPABLE,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            required_mounts=("FACTORY_DATA_DIR/memory/<factory_instance_id>",),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            port_env_key="MEMORY_MCP_PORT",
        ),
        "mcp-agent-bus": ServiceCatalogEntry(
            name="mcp-agent-bus",
            runtime_identity="mcp-agent-bus",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.SHARED_CAPABLE,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            required_mounts=("FACTORY_DATA_DIR/bus/<factory_instance_id>",),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            port_env_key="AGENT_BUS_PORT",
        ),
        "approval-gate": ServiceCatalogEntry(
            name="approval-gate",
            runtime_identity="approval-gate",
            service_kind=ServiceKind.SUPPORT_HTTP,
            scope=ServiceScope.SHARED_CAPABLE,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_http_semantics("/health"),
            repair_policy_class=RepairPolicyClass.CORE,
            port_env_key="APPROVAL_GATE_PORT",
        ),
        "agent-worker": ServiceCatalogEntry(
            name="agent-worker",
            runtime_identity="agent-worker",
            service_kind=ServiceKind.WORKER,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_worker_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
        ),
        "context7": ServiceCatalogEntry(
            name="context7",
            runtime_identity="context7",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            required_config_keys=("CONTEXT7_API_KEY",),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="context7",
            port_env_key="PORT_CONTEXT7",
        ),
        "bash-gateway-mcp": ServiceCatalogEntry(
            name="bash-gateway-mcp",
            runtime_identity="bash-gateway-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="bashGateway",
            port_env_key="PORT_BASH",
        ),
        "git-mcp": ServiceCatalogEntry(
            name="git-mcp",
            runtime_identity="git-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="git",
            port_env_key="PORT_FS",
        ),
        "search-mcp": ServiceCatalogEntry(
            name="search-mcp",
            runtime_identity="search-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="search",
            port_env_key="PORT_GIT",
        ),
        "filesystem-mcp": ServiceCatalogEntry(
            name="filesystem-mcp",
            runtime_identity="filesystem-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="filesystem",
            port_env_key="PORT_SEARCH",
        ),
        "docker-compose-mcp": ServiceCatalogEntry(
            name="docker-compose-mcp",
            runtime_identity="docker-compose-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="dockerCompose",
            port_env_key="PORT_COMPOSE",
        ),
        "test-runner-mcp": ServiceCatalogEntry(
            name="test-runner-mcp",
            runtime_identity="test-runner-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="testRunner",
            port_env_key="PORT_TEST",
        ),
        "offline-docs-mcp": ServiceCatalogEntry(
            name="offline-docs-mcp",
            runtime_identity="offline-docs-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(RuntimeProfileName.WORKSPACE_DEFAULT,),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="offlineDocs",
            port_env_key="PORT_DOCS",
        ),
        "github-ops-mcp": ServiceCatalogEntry(
            name="github-ops-mcp",
            runtime_identity="github-ops-mcp",
            service_kind=ServiceKind.MCP,
            scope=ServiceScope.WORKSPACE_SCOPED,
            profiles=(
                RuntimeProfileName.WORKSPACE_DEFAULT,
                RuntimeProfileName.HARNESS_DEFAULT,
            ),
            readiness=_mcp_semantics(),
            repair_policy_class=RepairPolicyClass.CORE,
            workspace_server_name="githubOps",
            port_env_key="PORT_GITHUB",
        ),
    }

    profiles = {
        RuntimeProfileName.WORKSPACE_DEFAULT: RuntimeProfile(
            name=RuntimeProfileName.WORKSPACE_DEFAULT,
            description=(
                "Full workspace runtime profile used by lifecycle inspection and "
                "operator-facing runtime surfaces."
            ),
            required_services=(
                "mock-llm-gateway",
                "mcp-memory",
                "mcp-agent-bus",
                "approval-gate",
                "agent-worker",
                "context7",
                "bash-gateway-mcp",
                "git-mcp",
                "search-mcp",
                "filesystem-mcp",
                "docker-compose-mcp",
                "test-runner-mcp",
                "offline-docs-mcp",
                "github-ops-mcp",
            ),
        ),
        RuntimeProfileName.HARNESS_DEFAULT: RuntimeProfile(
            name=RuntimeProfileName.HARNESS_DEFAULT,
            description=(
                "Harness-facing MCP subset used by FACTORY runtime consumers "
                "once they migrate behind the manager boundary."
            ),
            required_services=(
                "mcp-memory",
                "mcp-agent-bus",
                "git-mcp",
                "search-mcp",
                "filesystem-mcp",
                "github-ops-mcp",
            ),
        ),
    }

    return RuntimeCatalog(services=services, profiles=profiles)


DEFAULT_RUNTIME_CATALOG = build_catalog()
