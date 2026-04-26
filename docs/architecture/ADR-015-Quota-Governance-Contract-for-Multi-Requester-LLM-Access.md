# ADR-015: Quota-Governance Contract for Multi-Requester LLM Access

## Status

Accepted

## Context

The bounded immediate-repair umbrella `#139` established a workspace-global
throttle baseline for GitHub Models requests, shared queue-wait diagnostics,
and provider-feedback cooldown handling. That repair was necessary, but it does
not fully answer the long-term architecture question: many concurrent chats,
parent agents, child agents, and subagents can all share one upstream provider
surface.

Without an explicit long-term contract, later implementation slices can drift
into incompatible assumptions about who owns provider-facing quota authority,
what a subagent is allowed to consume, whether reserve capacity is per process
or shared, and whether a quota broker is allowed to masquerade as runtime
truth.

Those ambiguities are not acceptable in this repository:

- `ADR-013` requires architecture terms and authority boundaries to live in
  accepted ADRs rather than being redefined in plans or implementation notes.
- `ADR-008` prohibits assuming shared-service rollout without explicit tenant
  identity, isolation proof, and operator-visible diagnostics.
- `ADR-014` makes the MCP runtime manager authoritative for runtime lifecycle,
  readiness, and repair, which means the quota-governance path must not become
  a shadow runtime controller.

## Decision

### 1. One provider-facing quota-governance authority

- **Rule:** Provider-facing LLM request admission, shared quota state,
  provider-feedback cooldown propagation, and concurrency leasing MUST flow
  through one quota-governance authority.
- **Rule:** That authority MAY be implemented as a dedicated quota broker or a
  tightly scoped control-plane extension, but it MUST remain quota-governance
  authority only.
- **Rule:** The quota-governance authority MUST NOT redefine runtime lifecycle,
  runtime readiness, or runtime repair truth.
- **Rule:** The MCP runtime manager remains the authoritative owner of runtime
  lifecycle, readiness, and repair state.

### 2. Budget inheritance is hierarchical

- **Rule:** Provider-facing quota MUST be represented as a delegated hierarchy:
  `provider -> model family -> workspace -> run -> requester`.
- **Rule:** `provider` and `model family` define the upstream ceiling envelope.
- **Rule:** `workspace` is the default quota-governance authority boundary for
  this repository's current implementation baseline.
- **Rule:** `run` is the delegated budget root for one parent execution lineage.
- **Rule:** `requester` is the leaf budget consumer inside that lineage.
- **Rule:** Subagents MUST consume delegated budget through their parent `run`
  scope and MUST NOT be granted an independent provider entitlement.

### 3. The quota contract must represent multiple budget dimensions

- **Rule:** The quota-governance contract MUST represent at least these budget
  dimensions:
  - request-rate ceilings
  - token budgets
  - concurrency leases
- **Rule:** Provider/model-specific ceilings MUST be expressible without
  forcing every downstream scope to own an unrelated provider budget.
- **Rule:** Absence of a current token or concurrency number in one deployment
  does not remove the dimension from the contract; it remains part of the
  canonical vocabulary for later implementation slices.

### 4. Lanes are shared budget partitions, not per-process entitlements

- **Rule:** The architecture uses shared lane semantics such as `foreground`
  and `reserve` inside one delegated budget envelope.
- **Rule:** Lane capacity is shared across the relevant delegated scope; it is
  not a license for each process, client instance, chat, or subagent to open a
  fresh foreground or reserve budget independently.
- **Rule:** Reserve capacity exists to preserve bounded forward progress,
  starvation avoidance, retries, and recovery work under contention.

### 5. Workspace-scoped by default; shared rollout is deliberate

- **Rule:** The current quota-governance baseline is workspace-scoped by
  default.
- **Rule:** A future shared-service deployment is allowed only if it satisfies
  `ADR-008` tenant identity, storage/log partitioning, isolation proof, and
  operator-visible diagnostics.
- **Rule:** No document or implementation may claim that the quota-governance
  authority is broadly multi-tenant merely because the architecture leaves room
  for that promotion later.

### 6. Acceptance defines the contract, not rollout completion

- **Rule:** Acceptance of this ADR establishes the authority and hierarchy
  contract only.
- **Rule:** The immediate repair under umbrella `#139` remains a bounded
  near-term baseline and is not by itself the complete multi-requester
  architecture.
- **Rule:** Later issues in umbrella `#144` implement the contract in ordered
  slices:
  - `#141` brokered admission control and shared concurrency leases
  - `#142` requester-lineage fairness and shared provider feedback
  - `#143` observability and load validation
- **Rule:** Those later issues must build on this contract instead of reopening
  the authority question.

## Consequences

### Positive consequences

- The repository now has one reviewable source of truth for long-term
  quota-governance authority and vocabulary.
- Subagent behavior is constrained explicitly by parent lineage rather than by
  ad hoc implementation convention.
- Later implementation slices can add admission control, fairness,
  provider-feedback handling, and observability without redefining who owns
  quota authority.
- The architecture stays compatible with `ADR-008` and `ADR-014` instead of
  growing a second runtime authority.

### Trade-offs

- A real quota-governance implementation must now honor hierarchical budget
  inheritance instead of continuing with loosely coordinated client-local logic.
- Shared-service rollout remains slower because it requires explicit isolation
  proof rather than assumption.
- The contract introduces more vocabulary up front, which must now stay aligned
  across code, docs, and later issues.

## Non-goals

This ADR does not itself define:

- the exact scheduling algorithm for requester fairness
- the exact persistence backend for shared quota state
- the exact observability UI surface
- blanket cross-tenant rollout for quota governance
- any authority for runtime lifecycle, readiness, repair, or cleanup

## Decision summary

The repository adopts one quota-governance contract for multi-requester,
provider-facing LLM access. That contract establishes:

- one quota-governance authority distinct from runtime authority
- a delegated hierarchy of `provider -> model family -> workspace -> run -> requester`
- explicit representation for request-rate ceilings, token budgets, and
  concurrency leases
- shared `foreground` / `reserve` lane semantics inside one delegated budget
  envelope
- workspace-scoped default deployment with `ADR-008` guardrails for any later
  shared promotion
- and a clear separation between the bounded immediate repair under umbrella
  `#139` and the longer-term architecture/implementation queue under umbrella
  `#144`
