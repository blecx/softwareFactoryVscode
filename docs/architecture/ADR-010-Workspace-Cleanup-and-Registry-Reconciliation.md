# ADR-010: Workspace Cleanup and Registry Reconciliation

## Status

Proposed

## Context

The multi-workspace runtime registry (introduced in ADR-009) keeps track of installed, running, and active workspaces based on their port allocations and Docker identities. However, because a workspace is simply a cloned Git repository on a developer's machine with a `.factory.env` and `.softwareFactoryVscode` directory, a developer might aggressively delete the directory using `rm -rf` without explicitly tearing down the registry state.

This creates "stale" registry records that falsely reserve host-level port blocks indefinitely, leading to port exhaustion or collisions when new workspaces are provisioned. In addition, tearing down an active target manually via Docker Compose does not cleanly evict configuration tracking in the `.factory.env` or local runtime state.

## Decision

We implement an automatic implicit reconciliation framework supplemented by an explicit cleanup command.

### 1. Implicit Reconciliation on Discovery

- **Rule**: Any discovery action (e.g., `factory_stack.py list`) MUST run an automatic `reconcile_registry()` check before returning state.
- **Rule**: A registry entry is declared "stale" and evicted instantly if its Target Workspace Path no longer exists or if its generated runtime manifest is missing.

### 2. Explicit Cleanup command

- **Rule**: A `cleanup` command MUST be added to `factory_stack.py` (e.g., `python3 scripts/factory_stack.py cleanup`).
- **Rule**: `cleanup` MUST execute a deep obliteration which:
  1. Stops the local compose stack.
  2. Removes all attached Docker volumes (`docker compose down -v`).
  3. Deletes `.factory.env`, forcing a complete port release.
  4. Deletes the generated `runtime-manifest.json`.
  5. Scrapes the instance ID from the shared host registry explicitly.
- **Rule**: The command cleanly returns the repository into a pure Option B installation baseline without factory runtime state.

## Consequences

- Stale records automatically self-heal and release port blocks upon discovery queries.
- Developers have a safe, sanctioned command for obliterating a workspace instance fully without guessing which Docker volume mappings to `rm` manually.
- The throwaway testing environments and manual deletion workflows cannot permanently corrupt or exhaust host-level multi-workspace allocations.
