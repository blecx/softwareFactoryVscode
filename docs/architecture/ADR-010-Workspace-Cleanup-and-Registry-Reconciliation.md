# ADR-010: Workspace Cleanup and Registry Reconciliation

## Status

Accepted

## Context

The multi-workspace runtime registry introduced in ADR-009 tracks installed, running, and active workspaces using generated runtime metadata, compose project names, and per-workspace port blocks.

The canonical runtime contract for an installed workspace lives under `.copilot/softwareFactoryVscode/`, including:

- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/lock.json`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- configured workspace data directories referenced by `FACTORY_DATA_DIR`
- the generated host-facing `software-factory.code-workspace` bridge file

Operators can still create stale or partial state by deleting the host project or namespaced install directly, deleting generated `.tmp` artifacts without stopping the runtime, tearing down Docker manually, or leaving workspace-scoped data directories behind after runtime removal.

Because Docker bind mounts and host-level port reservations depend on these namespaced artifacts, cleanup and reconciliation must be explicit, namespace-first, and safe in partially broken environments.

## Decision

We implement automatic reconciliation plus an explicit cleanup command for runtime-state removal.

### 1. Implicit Reconciliation on Discovery

- **Rule:** Discovery commands such as `factory_stack.py list` MUST run registry reconciliation before returning state.
- **Rule:** A registry entry is stale if its target workspace path no longer exists, its generated runtime manifest is missing, or it points at invalid/non-dictionary registry data.
- **Rule:** Temporary throwaway validation workspaces may be evicted automatically once they are no longer active.
- **Rule:** If reconciliation removes the active workspace entry, the active selection MUST be cleared.

### 2. Explicit Cleanup command

- **Rule:** `factory_stack.py cleanup` removes runtime ownership and generated runtime artifacts, but it does not uninstall the `.copilot/softwareFactoryVscode/` checkout itself.
- **Rule:** Cleanup MUST stop the workspace compose stack with `down -v --remove-orphans` before deleting runtime artifacts when possible.
- **Rule:** Cleanup MUST remove the registry record, `.copilot/softwareFactoryVscode/.factory.env`, `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`, and workspace-scoped memory/bus data directories derived from `FACTORY_DATA_DIR`.
- **Rule:** Generated host-facing bridge files such as `software-factory.code-workspace` are not removed by runtime cleanup; they belong to the installed baseline and may be refreshed later by bootstrap/update flows.

### 3. Namespace-first runtime paths are authoritative

- **Rule:** Cleanup and reconciliation MUST treat `.copilot/softwareFactoryVscode/` as the canonical runtime namespace.
- **Rule:** Root-level `.factory.env`, `.factory.lock.json`, or hidden-tree `.softwareFactoryVscode/` artifacts MUST NOT be reintroduced as canonical cleanup targets.
- **Rule:** Cleanup semantics MUST remain consistent whether lifecycle commands are launched from the installed checkout or from the source checkout resolving the companion installed workspace contract.

### 4. Cleanup must be safe in hostile environments

- **Rule:** Cleanup SHOULD continue best-effort even if Docker teardown partially fails or the stack is already missing.
- **Rule:** Cleanup MUST still attempt to remove runtime contract artifacts and stale registry ownership when the runtime is only partially present.
- **Rule:** Image pruning remains a separate operator action and MUST NOT be conflated with workspace cleanup.

## Consequences

- Stale records automatically self-heal and release port blocks upon discovery queries.
- Operators have a sanctioned command for removing runtime state without guessing which namespaced artifacts or data directories to delete.
- Runtime cleanup returns a host repository to the namespace-first installed baseline without pulling the filesystem out from under running containers or reintroducing root-level factory sprawl.
- The throwaway testing environments and manual deletion workflows are less likely to corrupt or exhaust host-level multi-workspace allocations.
