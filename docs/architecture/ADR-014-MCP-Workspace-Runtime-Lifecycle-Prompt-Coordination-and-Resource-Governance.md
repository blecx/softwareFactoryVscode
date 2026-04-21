# ADR-014: MCP Workspace Runtime Lifecycle, Prompt Coordination, and Resource Governance

## Status

Proposed

## Context

The accepted ADR set already establishes the architectural baseline for:

- canonical runtime ownership under `.copilot/softwareFactoryVscode/`
- generated effective endpoints and port allocation
- the distinction between `installed`, `running`, and `active`
- cleanup and reconciliation semantics
- shared-mode promotion rules for shared-capable services
- document-authority hierarchy

Those rules are necessary, but they still leave one important gap: there is no
single authoritative MCP runtime contract that tells the rest of the system
what services exist, which profile is expected, whether the runtime is ready,
what is degraded, and what lifecycle action is allowed.

That gap matters because the coding/problem-solving harness should not be the
runtime authority. Prompt execution, task orchestration, and coding workflows
may depend on MCP services, but they should consume MCP runtime truth rather
than inventing it.

This ADR therefore defines a deliberately narrow implementation baseline:

- one authoritative MCP runtime manager/controller contract
- one machine-readable service catalog
- one canonical runtime snapshot with a two-layer state model
- static profile selection at prompt start
- one normative readiness contract
- one bounded repair ladder with reason codes
- one aligned artifact contract for `cleanup` and `delete-runtime`
- shared-service rules that apply only when a service is actually operating in
  shared mode under `ADR-008`
- checkpoint/resume coordination only at completed tool-call boundaries
- snapshot-first authority, with signals treated as secondary notifications

## Relationship to existing ADRs

This ADR extends but does not replace:

- `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`
- `ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`
- `ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md`
- `ADR-010-Workspace-Cleanup-and-Registry-Reconciliation.md`
- `ADR-011-Agent-Worker-Liveness-Contract.md`
- `ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `ADR-013-Architecture-Authority-and-Plan-Separation.md`

Per `ADR-013`, this ADR is normative only for the MCP runtime architecture that
it explicitly defines. It does not authorize plans, operator docs, or prompt
workflows to redefine the accepted meanings from earlier ADRs.

## Terms

- **MCP runtime manager**: the single authoritative runtime/controller contract
  for MCP service inventory, readiness, lifecycle, health, repair, and resource
  governance.
- **MCP service catalog**: the machine-readable source of truth for runtime
  services, their dependencies, their profiles, and their readiness rules.
- **Runtime snapshot**: the canonical, queryable state document for one
  workspace runtime identity.
- **Profile**: a named set of services required for a class of MCP use.
- **Activity lease**: renewable metadata showing that an operator-facing
  workspace surface is still in active use.
- **Execution lease**: renewable metadata showing that a prompt/session is
  actively executing or is paused while awaiting runtime repair.
- **Completed tool-call boundary**: a checkpoint after a tool call has either
  completed successfully or has failed with an explicit result, so replay safety
  can be reasoned about.
- **Shared mode**: a runtime mode where a shared-capable service is actually
  operating as shared infrastructure under the constraints of `ADR-008`.

## Decision

### 1. One authoritative MCP runtime manager/controller contract

- **Rule:** The system must have exactly one authoritative MCP runtime
  manager/controller contract for runtime truth.
- **Rule:** That authority is responsible only for MCP runtime concerns:
  service inventory, lifecycle, readiness, health, repair, leases, and resource
  governance.
- **Rule:** That authority must not be part of the coding/problem-solving
  harness.
- **Rule:** Prompt planning, coding, tool strategy, or other problem-solving
  behavior must not become the source of truth for MCP runtime state.
- **Rule:** Prompt/session layers may request lifecycle actions or query
  readiness, but they must consume runtime truth from the authoritative MCP
  runtime manager rather than maintaining a competing runtime contract.
- **Rule:** Regardless of implementation topology, only the authoritative MCP
  runtime manager may declare canonical readiness, canonical runtime state, or
  canonical repair outcome for a workspace runtime identity.
- **Rule:** `ADR-011` remains in force: the current `agent-worker` is a
  liveness placeholder and must not be treated as the authoritative controller
  unless a later implementation change says so explicitly.

### 2. One machine-readable service catalog

- **Rule:** The runtime must expose one machine-readable MCP service catalog as
  the source of truth for runtime services.
- **Rule:** Each service entry must declare at least:
  - logical name
  - runtime identity (such as Compose service name or equivalent)
  - service kind (`MCP`, support HTTP service, worker, or equivalent)
  - scope (`workspace-scoped`, `shared-capable`, or equivalent)
  - profile membership
  - dependency list
  - required mounts/resources
  - required config/secrets
  - readiness semantics
  - repair policy class (`core`, `optional`, or equivalent)
- **Rule:** Generated workspace settings, runtime verification, lifecycle
  orchestration, and operator diagnostics must derive from that same catalog.
- **Rule:** The catalog must present one consistent operator vocabulary even if
  current implementation names drift internally.

### 3. One canonical runtime snapshot with a two-layer state model

- **Rule:** The authoritative MCP runtime manager must expose one canonical
  runtime snapshot per canonical workspace identity.
- **Rule:** The runtime snapshot must be the authoritative state surface for
  runtime consumers.
- **Rule:** The snapshot must use a two-layer workspace model:

#### Layer A — lifecycle state

- **Rule:** Runtime lifecycle state must be distinct from operator selection and
  lease metadata.
- **Rule:** Runtime lifecycle state may be one of:
  - `starting`
  - `running`
  - `stopped`
  - `suspended`
  - `repairing`
  - `degraded`
  - `runtime-deleted`
- **Rule:** In the current practical baseline, `suspended` remains
  proposal-bound vocabulary only. Operator-facing status, output, and derived
  docs MUST NOT present suspend as a supported lifecycle state until explicit,
  test-backed suspend/resume semantics land in a later implementation slice.
- **Rule:** The accepted `installed` and `active` meanings from `ADR-009` are
  not redefined here.
- **Rule:** `installed` remains an architectural fact about the installed
  baseline, not a synonym for runtime lifecycle.
- **Rule:** `active` remains the explicit operator-selected workspace per
  `ADR-009`, not a synonym for `running`.

#### Layer B — selection and lease metadata

- **Rule:** The snapshot must separately record:
  - whether the workspace is the current `active` workspace per `ADR-009`
  - activity-lease presence and renewal metadata
  - execution-lease presence and renewal metadata
  - selected profile set
- **Rule:** Suspend or delete decisions must not rely only on stale activation
  timestamps.
- **Rule:** A workspace may be `active` without an execution lease.
- **Rule:** A workspace may hold an execution lease while the editor window is
  temporarily unfocused.
- **Rule:** A paused session awaiting runtime repair continues to hold its
  execution lease until the repair path resolves or the higher-level session is
  explicitly terminated.

#### Snapshot contents

- **Rule:** In addition to the two workspace layers, the snapshot must expose:
  - canonical workspace identity
  - last lifecycle transition and timestamp
  - per-service health/result records
  - blocking reason codes when present
  - latest readiness result
- **Rule:** Per-service records in the snapshot must distinguish current status
  from failure cause. For example, `degraded` or `stopped` is a status, while
  `missing-secret` or `dependency-unhealthy` is a reason code.
- **Rule:** When `cleanup` or `delete-runtime` removes the live runtime record
  per `ADR-010`, consumers must treat the absence of a live runtime record plus
  the continued installed baseline as a `runtime-deleted`/cold-start condition,
  not as a loss of architectural identity.

### 4. Static profile selection at prompt start

- **Rule:** The runtime must support profile-based startup and readiness rather
  than assuming a full stack for every prompt or workflow.
- **Rule:** A prompt/session must choose its required profile set before the
  first tool call that depends on the MCP runtime.
- **Rule:** This ADR does not require progressive profile expansion during a
  running prompt.
- **Rule:** If a prompt/session later requires services outside its selected
  profile set, the runtime manager must report a profile mismatch or not-ready
  result rather than silently mutating the profile set mid-execution.
- **Rule:** Handling of that mismatch in the higher-level UX is outside this
  ADR; the runtime contract is only that mid-execution profile expansion is not
  part of the baseline defined here.

### 5. Normative readiness contract

- **Rule:** Readiness must be defined normatively by the authoritative MCP
  runtime manager.
- **Rule:** A workspace runtime is ready for a selected profile only when all
  required services for that profile satisfy all of the following:
  - canonical workspace identity resolves correctly
  - declared dependencies are healthy enough for use
  - required config, secrets, and mounts are present
  - the service is reachable through its declared runtime endpoint
  - for MCP services, MCP `initialize` succeeds
  - for non-MCP support services, the declared health/readiness probe succeeds
- **Rule:** Socket reachability or container existence alone is not sufficient
  to declare readiness.
- **Rule:** Readiness results must return explicit reason codes when blocked,
  such as `missing-config`, `missing-secret`, `dependency-unhealthy`,
  `identity-mismatch`, `endpoint-unreachable`, `mcp-initialize-failed`, or
  `profile-mismatch`.
- **Rule:** Prompt/session layers must not proceed blindly when the runtime
  manager reports not-ready.

### 6. Bounded repair ladder with reason codes

- **Rule:** Repair must be dependency-aware, bounded, and cause-aware.
- **Rule:** Repair must prefer the smallest safe recovery boundary first.
- **Rule:** The baseline repair ladder is:

1. re-probe the affected service and dependencies
2. restart the affected service
3. recreate the affected service
4. repair a blocking dependency and retry readiness
5. reconcile runtime metadata/state drift if needed
6. surface terminal runtime failure with an operator-visible reason code

- **Rule:** Each step must use bounded retries and backoff.
- **Rule:** Repeated failure must trip a circuit-breaker condition rather than
  creating endless restart loops or silent livelock.
- **Rule:** Host-level failures such as Docker daemon outage, disk exhaustion,
  or host-network failure must be classified distinctly from service-local
  failures.
- **Rule:** Repair results must be visible through reason codes and timestamps
  in the runtime snapshot.

### 7. `cleanup` and `delete-runtime` share artifact effects and differ only by trigger

- **Rule:** `cleanup` and `delete-runtime` must have the same runtime-artifact
  effect.
- **Rule:** Both actions must preserve the installed baseline under
  `.copilot/softwareFactoryVscode/` per `ADR-010` and `ADR-012`.
- **Rule:** Both actions must remove live runtime ownership/resources so that a
  later use is a cold start.
- **Rule:** `cleanup` is the explicit operator-driven trigger.
- **Rule:** `delete-runtime` is the policy-driven trigger.
- **Rule:** Neither action implies host-global image pruning.

### 8. Shared-service rules apply only when a service is actually operating in shared mode

- **Rule:** `ADR-008` remains the authority for whether a service may operate in
  shared mode.
- **Rule:** Shared-service coordination rules in this ADR apply only when a
  shared-capable service is actually operating in shared mode under `ADR-008`.
- **Rule:** When a shared-capable service is still operating in per-workspace
  mode, readiness, repair, suspend, and delete decisions remain workspace-local.
- **Rule:** When a shared-capable service is operating in shared mode,
  suspend/delete decisions must aggregate dependent-workspace activity leases and
  execution leases rather than evaluating only one workspace in isolation.
- **Rule:** Shared-mode coordination must not be used to imply that every
  shared-capable service is always shared in the current implementation.

### 9. Prompt coordination is limited to completed tool-call boundaries

- **Rule:** The authoritative MCP runtime manager does not own prompt logic.
- **Rule:** Its role in prompt coordination is limited to reporting runtime
  readiness, runtime degradation, repair status, and whether resume is safe at a
  completed tool-call boundary.
- **Rule:** Automatic resume is allowed only from a completed tool-call
  boundary.
- **Rule:** This ADR does not authorize automatic replay from an ambiguous
  mid-call state.
- **Rule:** If a mutating tool call is interrupted and execution status is
  ambiguous, the runtime manager must report that resume is unsafe unless the
  higher-level workflow can prove replay safety through explicit operation
  identity or equivalent evidence.

### 10. State snapshot is authoritative; signals are secondary

- **Rule:** The runtime snapshot is the authoritative source of current truth.
- **Rule:** Signals are secondary notifications only.
- **Rule:** Missing, delayed, duplicated, or out-of-order signals must not be
  treated as a license to override the current snapshot.
- **Rule:** Any signal transport is implementation-specific and non-normative in
  this ADR.
- **Rule:** Signals may still be emitted for operator UX or coordination, but
  consumers must reconcile against the authoritative snapshot before making
  consequential decisions.

## Consequences

### Positive consequences

- MCP runtime truth becomes explicit and centralized.
- The coding/problem-solving harness no longer has to double as runtime
  authority.
- Readiness and repair become reviewable and testable against one contract.
- `ADR-009` and `ADR-010` semantics remain intact instead of being blurred by a
  new aggregate state enum.
- Shared-service behavior becomes conditional and precise instead of assumed.
- The baseline is implementable without taking on dynamic profile expansion,
  image-mutation policy, or a large event-system design.

### Trade-offs

- A real authoritative runtime contract must now exist instead of ad hoc status
  checks.
- Prompt/session layers must integrate with runtime truth rather than bypassing
  it.
- Repair and readiness logic become formal responsibilities that must be
  implemented and tested.

## Non-goals

This ADR does not define:

- prompt planning, coding behavior, or problem-solving strategy
- the specific process/binary/component name that implements the authoritative
  MCP runtime manager
- dynamic profile expansion during a running prompt
- automatic image pull/upgrade policy
- the exact signal transport
- the exact UI surface for runtime state
- the exact checkpoint storage format
- host-global image pruning policy

## Decision summary

The architecture must provide one authoritative MCP-only runtime contract that
is separate from the coding/problem-solving harness and that defines:

- one machine-readable service catalog
- one canonical runtime snapshot
- a two-layer workspace model of lifecycle state plus selection/lease metadata
- static profile selection at prompt start
- normative readiness based on dependency health, MCP `initialize`, and required
  config presence
- bounded repair with reason codes
- aligned `cleanup` and `delete-runtime` artifact semantics
- shared-service lease aggregation only when a service is actually operating in
  shared mode under `ADR-008`
- checkpoint/resume coordination only at completed tool-call boundaries
- snapshot-first runtime authority with signals treated as secondary

This ADR is intended to be complete enough for implementation without growing
into a general prompt-orchestration architecture.
