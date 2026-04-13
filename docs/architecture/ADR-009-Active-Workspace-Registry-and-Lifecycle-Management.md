# ADR-009: Active Workspace Registry and Lifecycle Management

## Status

Accepted

## Context

The repository now maintains installation and runtime metadata inside each target project under `.copilot/softwareFactoryVscode/`, but multi-workspace operation still requires a first-class host-level model for tracking which installed workspaces are present, which are running, which one is active for operator workflows, and which ports and compose projects they own.

Throwaway validation and source-checkout tooling can invoke the lifecycle from different entrypoints, so the runtime needs one shared registry and one shared identity model rather than multiple ad hoc workspace assumptions.

## Decision

We will add a host-level active-workspace registry and lifecycle model.

### 1. Installed, running, and active are distinct states

- **Rule:** The system MUST distinguish installed workspaces, running workspaces, and active workspaces.
- **Rule:** Active workspace selection MUST be explicit and operator-visible.

### 2. A host-level registry is the source of truth for runtime ownership

- **Rule:** The runtime lifecycle MUST maintain a host-scoped registry that records workspace identity, path, compose project name, port block, and status.
- **Rule:** Runtime lifecycle commands MUST update this registry atomically.

### 3. The installed workspace contract is the canonical runtime identity surface

- **Rule:** Registry records MUST resolve to the installed workspace contract under `.copilot/softwareFactoryVscode/`, including the namespaced factory path and generated workspace file path.
- **Rule:** Lifecycle commands invoked from the installed checkout or from the source checkout MUST resolve to the same installed workspace identity, compose project, port block, and runtime manifest.
- **Rule:** Source-checkout tooling may operate the companion installed workspace, but it MUST NOT create a second competing runtime identity or static MCP runtime contract.

### 4. Lifecycle commands replace ad hoc workspace switching

- **Rule:** Operators and automated validation flows SHOULD use shared lifecycle commands to list, start, stop, activate, deactivate, and clean up workspaces.
- **Rule:** Throwaway validation and future workspace switching logic SHOULD reuse the same lifecycle machinery instead of custom stop/start sequences.

### 5. Cleanup semantics must be explicit

- **Rule:** Container removal, volume removal, and image pruning MUST remain distinct operations.
- **Rule:** The lifecycle UX MUST make it obvious whether a command stops containers only, removes volumes, or prunes images.

## Consequences

- Multiple installed workspaces become manageable rather than implicit.
- Operators can understand which workspace owns which runtime resources.
- Source-checkout lifecycle invocations and installed-workspace lifecycle invocations converge on one runtime identity instead of competing contracts.
- The repository gains a clean foundation for multi-workspace operation before shared multi-tenant services are introduced.
