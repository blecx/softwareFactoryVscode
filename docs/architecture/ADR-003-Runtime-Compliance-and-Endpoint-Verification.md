# ADR-003: Runtime Compliance & Endpoint Verification

## Status

Accepted

## Context

Install-time compliance proves that the hidden-tree layout, host-side files, and Option B workspace entrypoint are correct. It does not prove that the runtime stack is actually running or that the local endpoints required by the workflow are reachable.

Once an operator starts the factory services, we need a second, explicit compliance phase that checks runtime health without mutating the target repository.

## Decisions

### 1. Runtime Compliance is a Distinct Verification Phase

Runtime verification MUST be available as an explicit mode of the installation verifier.

- **Rule:** `scripts/verify_factory_install.py` MUST support a runtime verification mode.
- **Rule:** Runtime verification MUST be opt-in because the service stack is not expected to be running immediately after installation.
- **Rule:** Runtime verification failures MUST fail the verifier invocation.

### 2. Core Factory Runtime Must Be Checked First

The runtime verifier MUST validate the documented core compose stack before any higher-level endpoint checks.

- **Rule:** Verify that the compose project identified by `COMPOSE_PROJECT_NAME` has the required running services.
- **Rule:** Services with Docker health checks MUST be reported healthy.
- **Rule:** Core health endpoints (memory, agent bus, approval gate, and any other documented health endpoints in the compose contract) MUST be reachable.

### 3. VS Code MCP Endpoint Checks are Optional Runtime Assertions

The local MCP endpoints used by VS Code are valuable to test, but they may not always be part of the exact runtime the operator started.

- **Rule:** The runtime verifier MUST offer an optional mode to check localhost MCP endpoints configured in the VS Code agent settings.
- **Rule:** MCP endpoint reachability checks MUST be opt-in and MUST remain read-only.

### 4. Runtime Smoke Testing Must Remain Non-Mutating

- **Rule:** Successful runtime verification SHOULD print a non-mutating smoke prompt focused on container state and endpoint reachability.
- **Rule:** The smoke prompt MUST explicitly forbid file edits and runtime state changes.

## Consequences

- Operators now have a repeatable way to prove not only that the installation exists, but that the runtime is actually alive.
- Runtime verification remains strict without forcing operators to start containers during installation.
- The install verifier becomes a two-phase compliance tool: install contract first, runtime contract second.
