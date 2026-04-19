# ADR-008: Hybrid Tenancy Model for MCP Services

## Status

Accepted

## Context

Not all MCP services in `softwareFactoryVscode` have the same tenancy shape.

Some services mount one repository at `/target` and are therefore naturally workspace-scoped. Others operate more like shared control-plane services and can plausibly evolve into multi-tenant services if they enforce explicit workspace identity and storage isolation.

Treating all MCP services as if they were either fully single-tenant or fully multi-tenant would create unsafe assumptions.

## Decision

We adopt a hybrid tenancy model.

### 1. Workspace-scoped services remain single-tenant by default

- **Rule:** Services that depend on one mounted repository root or direct project filesystem state MUST remain one-instance-per-workspace until redesigned.
- **Rule:** This includes services such as bash gateway, repo fundamentals servers, offline docs, GitHub ops, docker-compose MCP, and test runner MCP.

### 2. Shared control-plane services may be promoted to multi-tenant status deliberately

- **Rule:** Candidate shared services such as memory, agent bus, and approval gate MAY become multi-tenant only after they implement explicit tenant identity, storage partitioning, and audit isolation.
- **Rule:** Multi-tenant services MUST reject ambiguous requests that do not include tenant identity.

### 3. Multi-tenant promotion requires isolation proof

- **Rule:** A service MUST NOT be treated as multi-tenant-capable until cross-tenant isolation is covered by tests and operator-visible diagnostics.
- **Rule:** Logs, metrics, audit records, and storage paths MUST be partitioned by tenant identity.

### 4. Acceptance does not itself mark rollout complete

- **Rule:** Accepting this ADR makes the hybrid-tenancy guardrails normative architecture, but it does not by itself mean that shared-service promotion is fulfilled in code, runtime topology, or release status.
- **Rule:** Candidate shared services such as memory, agent bus, and approval gate MUST NOT be described as fully promoted shared-control-plane infrastructure until the rollout criteria below are satisfied in implementation and verification.
- **Rule:** Rollout criteria include explicit tenant identity end to end, rejection of ambiguous requests, partitioned storage/logs/audit paths, cross-tenant regression coverage, and operator-visible diagnostics.

## Consequences

- The architecture can support multiple active workspaces immediately through multiple isolated stacks.
- Shared-service optimization becomes possible later without weakening repository isolation for workspace-bound services.
- The design avoids forcing unsafe multi-tenancy onto services that still assume a single `/target` workspace.
- The repository now has an accepted architectural guardrail set for hybrid tenancy, while the shared-service rollout remains an implementation and verification program rather than an implicit done claim.
