# ADR 007: Multi-Workspace and Hybrid Tenancy Model

## Status
Accepted

## Context
With the introduction of the active-workspace registry and generated effective endpoints, `softwareFactoryVscode` now supports multiple isolated workspaces running on the same host. Moving forward, some MCP services (like offline-docs or large LLM context-gatherers) should be shared across workspaces to save host resources, while others (like bash gateways or filesystem tools) must remain strictly scoped to a single repository for safety.

## Decision
We classify the factory services into two groups:

1. **Workspace-Scoped Single-Tenant Services:**
   - E.g., `mcp-bash-gateway`, `mcp-devops`, `mcp-github-ops`
   - Bound to a specific `/target` directory.
   - Run per-workspace in isolated docker compose projects (`factory_<target-name>`).

2. **Candidate Shared Multi-Tenant Services:**
   - E.g., `context7`, `mcp-offline-docs`
   - Shared across all workspaces on the host.
   - **Explicit Tenant Contract:** Before any candidate service is promoted to run in a globally shared docker-compose stack, it MUST validate an `X-Tenant-ID` header (or equivalent) for all requests, ensuring that multi-tenant scopes do not leak data across workspaces.

For now, all services default to Workspace-Scoped Single-Tenant deployment to preserve isolated verification coverage. Candidate shared services are documented as such, but their multi-tenant implementation will be deferred until the explicitly defined tenant contract is fully enforced in their runtime.

## Consequences
- Operators can distinguish installed, running, and active workspaces using the `factory_workspace.py status` CLI.
- Single-tenant isolation is the safe default.
- We establish the contract for hybrid tenancy without breaking existing pipelines.
