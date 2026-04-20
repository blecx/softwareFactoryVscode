# MCP Runtime Manager Implementation Plan

## Status

Proposed sequencing plan

This document is an implementation plan, not an ADR.

- Per `ADR-013`, accepted ADRs define architecture rules, terminology, and guardrails.
- Per `ADR-014`, the MCP runtime contract is normative architecture; this plan only sequences implementation.
- This plan MUST NOT be cited as a competing architecture source, MUST NOT be renumbered as an ADR, and MUST NOT be used to redefine accepted terms such as `installed`, `running`, `active`, shared mode, readiness, or cleanup semantics.
- If this plan conflicts with an accepted ADR or with verified implementation that intentionally moved beyond the plan, the plan must be corrected; it does not win by existing.

## Objective

Deliver the first authoritative MCP runtime manager as a dedicated subsystem that:

- owns MCP runtime truth,
- is not part of the problem-solving/coding harness,
- preserves the current workspace contract under `.copilot/softwareFactoryVscode/`, and
- is small enough to implement safely without under-scoping a critical harness dependency.

The goal of this plan is not to redesign the whole system. The goal is to land the `ADR-014` baseline cleanly and make the next execution stretch concrete.

## Scope for this plan

### In scope

- one authoritative MCP runtime manager/controller contract;
- one machine-readable service catalog;
- one canonical runtime snapshot with lifecycle state plus selection/lease metadata;
- static profile selection at prompt start;
- normative readiness based on dependency health, required config, and MCP `initialize`;
- a bounded repair ladder with reason codes;
- one shared implementation path for `cleanup` and `delete-runtime` artifact effects;
- migration of the harness/agent layer into a runtime consumer rather than a runtime authority.

### Explicitly out of scope for this plan

- dynamic profile expansion during a running prompt;
- image pull/upgrade policy automation;
- a full signal/event transport design;
- UI design for runtime state;
- broad prompt orchestration changes unrelated to MCP runtime authority;
- introducing new architecture decisions without updating the relevant ADR first.

## Current code starting point

The current implementation already has the raw pieces the new manager should stand on.

| Surface                                   | Current role                                                                                                                       | Planning implication                                                                                    |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `scripts/factory_workspace.py`            | Builds runtime config, manifest, topology, registry records, and generated workspace artifacts                                     | Keep as low-level persistence/projection utilities; do not leave runtime policy scattered here forever. |
| `scripts/factory_stack.py`                | Current lifecycle CLI and runtime inspection (`start`, `stop`, `list`, `status`, `preflight`, `activate`, `deactivate`, `cleanup`) | Preserve the CLI surface, but route runtime truth through the new manager.                              |
| `scripts/verify_factory_install.py`       | Compliance and runtime verification                                                                                                | Make it consume the same readiness/snapshot contract as lifecycle commands.                             |
| `factory_runtime/agents/mcp_lifecycle.py` | Current bootloader inside the agent layer                                                                                          | Convert into a thin consumer/adapter so runtime authority no longer lives in the harness.               |
| `factory_runtime/agents/factory.py`       | Loads workspace identity and server URLs from manifest/env fallbacks                                                               | Replace ad hoc endpoint/runtime truth logic with manager-backed accessors.                              |
| `tests/test_factory_install.py`           | Current lifecycle, preflight, shared-mode, and cleanup regression coverage                                                         | Extend rather than bypass; this is the main safety net for the rollout.                                 |
| `tests/test_regression.py`                | Locks authority/doc wording                                                                                                        | Use it to keep this plan explicitly non-normative.                                                      |

## Execution guardrails

- Preserve the meanings of `installed`, `running`, and `active` from `ADR-009`.
- Preserve canonical runtime ownership under `.copilot/softwareFactoryVscode/` from `ADR-012`.
- Do not create a second runtime authority in the agent/problem-solving layer.
- Keep `scripts/factory_stack.py` commands stable while the new manager is introduced.
- Treat the runtime snapshot as authoritative and any signals as secondary.
- Apply shared-service rules only when a service is actually operating in shared mode under `ADR-008`.
- Keep `cleanup` and `delete-runtime` on one artifact-effect path; only the trigger/reason differs.
- Treat completed tool-call boundaries as the only allowed automatic resume boundary in this baseline.
- Do not widen scope to dynamic profiles, image policy, or broad orchestration while the manager baseline is still landing.

## Target module layout for the first implementation

Create a dedicated MCP-runtime package outside `factory_runtime/agents/`.

Recommended initial layout:

```text
factory_runtime/mcp_runtime/
  __init__.py
  models.py       # typed runtime snapshot, readiness, reason-code, and catalog models
  catalog.py      # machine-readable service catalog and static profile mapping
  manager.py      # authoritative runtime manager/controller contract
  repair.py       # bounded repair ladder helpers (or keep internal to manager initially)
```

Adapter surfaces should remain, but become thin:

- `scripts/factory_stack.py` → CLI adapter over the manager
- `scripts/verify_factory_install.py` → verifier consumer of manager readiness/snapshot
- `factory_runtime/agents/mcp_lifecycle.py` → harness-side bootloader adapter only
- `factory_runtime/agents/factory.py` → consumer of manager-backed runtime endpoint access

## Delivery phases

### Phase 1: Establish the manager package and contract

**Goal:** Introduce one dedicated MCP-runtime authority without changing operator-facing lifecycle commands yet.

#### Phase 1 tasks

1. Add `factory_runtime/mcp_runtime/` with typed models for:
   - service catalog entries,
   - selected profile set,
   - runtime lifecycle state,
   - selection/lease metadata,
   - readiness result,
   - repair result and reason codes,
   - runtime snapshot.
2. Define `MCPRuntimeManager` as the authoritative contract with methods equivalent to:
   - `load_catalog(...)`
   - `build_snapshot(...)`
   - `evaluate_readiness(...)`
   - `start(...)`
   - `stop(...)`
   - `cleanup(trigger=...)`
   - `repair(...)`
3. Keep the initial implementation intentionally thin by delegating to proven helpers in `factory_workspace.py` and `factory_stack.py` instead of rewriting everything at once.
4. Normalize reason codes and status names in one place so later consumers stop inventing their own strings.

#### Phase 1 definition of done

- The repo has one importable MCP-runtime package outside the agent layer.
- The manager contract can build a canonical snapshot for a workspace identity.
- The service catalog and static profile model exist in one place.
- No operator-facing command surface changes are required yet.

#### Phase 1 validation

- Add focused tests for catalog loading, snapshot assembly, and reason-code normalization.
- Re-run the existing lifecycle tests to confirm no behavior drift.

### Phase 2: Move runtime truth behind the manager

**Goal:** Make lifecycle status, preflight, and runtime verification consume one shared runtime truth source.

#### Phase 2 tasks

1. Refactor `scripts/factory_stack.py` so `preflight`, `status`, `start`, `stop`, and `cleanup` call the manager for runtime truth instead of recomputing it ad hoc.
2. Keep `scripts/factory_workspace.py` focused on persistence/projection concerns such as:
   - env parsing/writing,
   - runtime manifest projection,
   - registry IO,
   - generated workspace file sync.
3. Refactor `scripts/verify_factory_install.py` to consume the manager's readiness result and runtime snapshot instead of duplicating runtime health rules.
4. Keep the current CLI verb surface unchanged during this migration.

#### Phase 2 definition of done

- `factory_stack.py preflight` and `factory_stack.py status` derive readiness/state from the same manager-backed snapshot.
- `verify_factory_install.py` uses the same readiness contract as lifecycle inspection.
- Reason codes and status outputs are consistent across CLI and verifier.

#### Phase 2 validation

- Extend `tests/test_factory_install.py` around preflight, status, shared topology, and verify-runtime flows.
- Re-run `tests/test_factory_install.py` and `tests/test_regression.py`.

### Phase 3: Remove runtime authority from the harness layer

**Goal:** Make the harness a consumer of MCP runtime truth instead of an owner of runtime lifecycle logic.

#### Phase 3 tasks

1. Refactor `factory_runtime/agents/mcp_lifecycle.py` so it becomes a thin adapter over the manager:
   - it may request readiness/start/stop,
   - but it must no longer decide what runtime truth is.
2. Refactor `factory_runtime/agents/factory.py` so workspace identity and runtime server URLs come from manager-backed snapshot/accessor paths rather than ad hoc manifest/env fallback logic scattered in the agent layer.
3. Preserve source-checkout companion-runtime behavior, but move its resolution logic behind the manager boundary.
4. Keep compatibility shims only where needed for rollout safety; remove duplicate truth paths where practical.

#### Phase 3 definition of done

- No agent-layer module is the authoritative source of runtime readiness or endpoint truth.
- The manager is the only authority for runtime URLs, readiness, and runtime state.
- The existing bootloader behavior still works, but as an adapter rather than a controller.

#### Phase 3 validation

- Extend the existing `MCPBootloader` regression coverage to verify manager-backed resolution.
- Re-run the source-checkout companion-runtime tests in `tests/test_factory_install.py`.

### Phase 4: Land the bounded repair and cleanup/delete-runtime baseline

**Goal:** Finish the minimal `ADR-014` baseline without drifting into a giant orchestration project.

#### Phase 4 tasks

1. Implement the bounded repair ladder inside the manager with explicit reason codes for:
   - re-probe,
   - restart,
   - recreate,
   - dependency repair failure,
   - metadata drift reconciliation,
   - terminal failure.
2. Add a shared implementation path for manual `cleanup` and policy-triggered `delete-runtime`, with the trigger recorded as metadata/reason rather than separate artifact logic.
3. Expose selection/lease metadata in the snapshot even if policy-driven timers remain minimal at first.
4. Add the minimal completed-tool-call boundary contract needed for higher layers to classify interruption recovery as:
   - `resume-safe`,
   - `resume-unsafe`, or
   - `manual-recovery-required`.
5. Do **not** add dynamic profile expansion or ambiguous mid-call replay in this phase.

#### Phase 4 definition of done

- Repair is bounded and reason-coded instead of open-ended.
- `cleanup` and `delete-runtime` share one artifact-effect path.
- The snapshot exposes enough lease/recovery metadata for higher-level consumers to make correct decisions.

#### Phase 4 validation

- Add targeted tests for repair escalation, cleanup/delete-runtime parity, and recovery classification boundaries.
- Re-run lifecycle and cleanup regressions.

## Recommended execution order for the next implementation stretch

1. **Phase 1 first** — create the dedicated manager package and types.
2. **Phase 2 next** — route `preflight`, `status`, and verifier logic through the manager.
3. **Phase 3 after that** — convert the harness bootloader/orchestrator layer into a consumer only.
4. **Phase 4 last** — add bounded repair and cleanup/delete-runtime parity once authority centralization is already stable.

Do not start by editing prompt agents or planner logic. The first win is centralizing MCP runtime truth.

## Quality gates

Before marking this plan's execution slice complete, run at minimum:

1. `tests/test_factory_install.py`
2. `tests/test_regression.py`
3. targeted shared-topology and cleanup parity cases touched by the manager rollout
4. the relevant runtime verification path through `scripts/verify_factory_install.py`

Recommended add-on gate for the final slice:

- `✅ Validate: Local CI Parity`

## First slice recommendation

The smallest adequate first slice is:

1. create `factory_runtime/mcp_runtime/` with typed models, catalog, and manager contract;
2. make `factory_stack.py preflight` and `factory_stack.py status` call the manager;
3. keep the existing CLI verbs and registry format stable;
4. leave dynamic profiles, image policy, and advanced resume logic for later slices.

That slice is small enough to land safely, but important enough to establish the critical architectural boundary: the MCP runtime has one authority, and it is not the coding harness.

## Exit condition for this plan

This plan is successful when the repository has one dedicated MCP runtime authority that:

- is separate from the harness agent layer,
- owns service catalog, readiness, snapshot, and repair truth,
- is consumed consistently by lifecycle CLI, runtime verification, and harness bootstrapping,
- preserves the accepted workspace contract and current lifecycle semantics, and
- is covered by regression tests strong enough to prevent a quiet slide back into multiple runtime authorities.
