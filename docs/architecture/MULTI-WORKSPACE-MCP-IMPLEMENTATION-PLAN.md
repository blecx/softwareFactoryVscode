# Multi-Workspace and Multi-Tenant MCP Implementation Plan

## Status

Proposed

## Objective

Implement a robust runtime and configuration model that allows multiple `softwareFactoryVscode` workspaces to coexist on one host, run concurrently when desired, and evolve selected MCP services into safe multi-tenant shared services.

## Success Criteria

- A workspace install produces a stable workspace identity and a stable effective port map.
- VS Code MCP settings for an installed workspace point to the workspace’s effective runtime endpoints.
- Runtime verification succeeds against the effective endpoints rather than hardcoded defaults.
- Operators can list, start, stop, and inspect installed workspaces without guessing which one owns localhost ports.
- Workspace-scoped MCP services remain isolated.
- Shared services promoted to multi-tenant mode enforce tenant isolation.

## Workstreams

## Workstream 1: Workspace Identity and Registry

### Workstream 1 Deliverables

- host-scoped registry file format,
- `FACTORY_INSTANCE_ID` allocation,
- workspace metadata projection during install/update,
- stale-entry recovery rules.

### Workstream 1 Detailed Steps

1. Define registry schema with:
   - workspace path,
   - workspace file path,
   - compose project name,
   - instance ID,
   - port block,
   - runtime status,
   - last activated timestamp,
   - version/commit metadata.
2. Add registry create/update hooks to install/update/bootstrap.
3. Add idempotent registry refresh command for existing installs.
4. Add stale-record reconciliation against filesystem and Docker state.

### Workstream 1 Robustness Checks

- registry write is atomic,
- duplicate instance IDs are rejected,
- missing registry can be rebuilt from project-local metadata.

## Workstream 2: Port Allocation and Effective Endpoint Generation

### Workstream 2 Deliverables

- canonical per-workspace port block allocator,
- persisted port variables in `.factory.env`,
- generated workspace MCP URLs,
- generated health endpoint map.

### Workstream 2 Detailed Steps

1. Define canonical offsets for all published services.
2. Add allocator that:
   - prefers deterministic allocation,
   - verifies host-port availability,
   - retries safely when a block is unavailable.
3. Write effective port values into `.factory.env` during install/update or activation.
4. Replace hardcoded MCP URLs in generated workspace settings with URLs derived from the effective ports.
5. Extend runtime verification to probe those generated URLs and effective health ports.

### Workstream 2 Robustness Checks

- verification must fail with clear diagnostics when a required port is missing or inconsistent,
- regenerated settings must be deterministic and idempotent,
- compose and workspace settings must not drift.

## Workstream 3: Active Workspace Operations

### Workstream 3 Deliverables

- operator commands to list/start/stop/activate/deactivate workspaces,
- clear distinction between installed, running, and active states,
- compatibility with throwaway validation.

### Workstream 3 Detailed Steps

1. Add commands such as:
   - `workspace list`,
   - `workspace status`,
   - `workspace activate`,
   - `workspace stop`,
   - `workspace cleanup`.
2. Make activation regenerate workspace settings and ensure the runtime endpoint map is current.
3. Make stop/cleanup update registry state.
4. Update throwaway validation to use the same lifecycle manager rather than ad hoc start/stop sequencing.

### Workstream 3 Robustness Checks

- active status must survive process restarts,
- stopping one workspace must not corrupt another workspace registry record,
- cleanup must clearly separate container removal from image pruning.

## Workstream 4: Hybrid Tenancy Classification

### Workstream 4 Deliverables

- service classification matrix,
- shared-service tenant contract,
- migration plan for candidate shared services.

### Workstream 4 Detailed Steps

1. Mark current services as either:
   - workspace-scoped single-tenant,
   - or candidate shared multi-tenant.
2. Freeze workspace-scoped services behind the `/target` isolation rule until redesigned.
3. Define shared-service request contract using explicit tenant identity in headers or equivalent transport metadata.
4. Define storage partition rules for shared services.
5. Add cross-tenant regression tests before any shared-service rollout.

### Workstream 4 Robustness Checks

- no shared service can read or write data without a tenant identity,
- no tenant can observe another tenant’s logs or records by default.

## Workstream 5: Documentation and Verification

### Workstream 5 Deliverables

- updated install docs,
- updated runtime docs,
- updated verification rules,
- ADR adoption trail.

### Workstream 5 Detailed Steps

1. Update `docs/INSTALL.md` to explain workspace-specific ports and active-workspace commands.
2. Update runtime verification documentation to reference generated endpoints.
3. Add architecture and ADR references to future issue/PR planning.
4. Add tests covering:
   - install/update of port maps,
   - generated MCP URLs,
   - runtime verification with non-default ports,
   - registry lifecycle,
   - multi-tenant request isolation for promoted services.

## Delivery Phases

### Phase A: Foundation

- workspace identity,
- registry schema,
- port block model,
- settings generation design.

### Phase B: Single-Host Multi-Workspace Support

- `.factory.env` port projection,
- workspace MCP URL generation,
- verification updates,
- active-workspace commands.

### Phase C: Operational Hardening

- stale registry reconciliation,
- cleanup semantics,
- throwaway/runtime handoff integration,
- documentation refresh.

### Phase D: Shared Multi-Tenant Services

- tenant-aware memory,
- tenant-aware agent bus,
- tenant-aware approval gate,
- isolation tests and operator diagnostics.

## Recommended Order of Implementation

1. workspace identity and registry,
2. port allocation and generated settings,
3. verification and lifecycle commands,
4. throwaway/runtime workflow integration,
5. multi-tenant shared-service promotion.

## Risks and Mitigations

### Risk: configuration drift between compose and VS Code settings

Mitigation: generate both from the same effective runtime metadata.

### Risk: stale or conflicting port allocations

Mitigation: registry reconciliation plus pre-start port availability checks.

### Risk: operator confusion about active vs running workspace

Mitigation: explicit commands and status reporting for installed/running/active states.

### Risk: accidental cross-tenant data leakage in shared services

Mitigation: do not promote a service to shared status without explicit tenant contract, storage partitioning, and cross-tenant tests.

### Risk: migration breaks existing installs

Mitigation: provide compatibility defaults for current single-workspace installs and add an upgrade path that backfills registry and port metadata.

## Exit Conditions

This plan is complete when a user can install two projects on one host, run both stacks with distinct effective endpoints, open each workspace in VS Code with correct MCP URLs, verify each runtime independently, and optionally use approved shared multi-tenant control plane services without tenant leakage.
