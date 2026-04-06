# ADR-009: Active Workspace Registry and Lifecycle Management

## Status

Proposed

## Context

Today the repository has installation metadata inside each target project, but it lacks a first-class host-level model for tracking which workspaces are installed, which are running, which one is active for operator workflows, and which ports and compose projects they own.

Throwaway validation already performs temporary stop/start handoff logic, but it does so procedurally rather than through a shared runtime registry and lifecycle contract.

## Decision

We will add a host-level active-workspace registry and lifecycle model.

### 1. Installed, running, and active are distinct states

- **Rule:** The system MUST distinguish installed workspaces, running workspaces, and active workspaces.
- **Rule:** Active workspace selection MUST be explicit and operator-visible.

### 2. A host-level registry is the source of truth for runtime ownership

- **Rule:** The runtime lifecycle MUST maintain a host-scoped registry that records workspace identity, path, compose project name, port block, and status.
- **Rule:** Runtime lifecycle commands MUST update this registry atomically.

### 3. Lifecycle commands replace ad hoc workspace switching

- **Rule:** Operators and automated validation flows SHOULD use shared lifecycle commands to list, start, stop, activate, deactivate, and clean up workspaces.
- **Rule:** Throwaway validation and future workspace switching logic SHOULD reuse the same lifecycle machinery instead of custom stop/start sequences.

### 4. Cleanup semantics must be explicit

- **Rule:** Container removal, volume removal, and image pruning MUST remain distinct operations.
- **Rule:** The lifecycle UX MUST make it obvious whether a command stops containers only, removes volumes, or prunes images.

## Consequences

- Multiple installed workspaces become manageable rather than implicit.
- Operators can understand which workspace owns which runtime resources.
- The repository gains a clean foundation for multi-workspace operation before shared multi-tenant services are introduced.

