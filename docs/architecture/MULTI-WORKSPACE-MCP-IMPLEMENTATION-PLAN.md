# Multi-Workspace and Multi-Tenant MCP Implementation Plan

## Status

Proposed

This document is a sequencing plan, not the normative source of architecture
truth. Per `ADR-013`, accepted ADRs define architecture guardrails and
terminology, architecture synthesis documents may explain but not override them,
and plans remain authoritative only for sequencing and hardening work. Accepted
runtime contracts now live in `ADR-012`, accepted
`ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`, `ADR-008`,
`ADR-009`, and `ADR-010`. `ADR-007-Multi-Workspace-and-Shared-Services.md` is
retained only as a superseded historical note for traceability; it is not a
second active ADR-007 authority source. `ADR-008` is now accepted and defines
the hybrid-tenancy guardrails; this plan sequences the remaining rollout work
required before shared-service promotion can be described as fulfilled in
releases or operator guidance. `MULTI-WORKSPACE-MCP-ARCHITECTURE.md` is a
maintained architecture synthesis that explains how those decisions fit
together and maps them onto the current codebase. When this plan or that
synthesis lags, the accepted ADRs and verified code are the source of truth.

Status note (2026-04-19): the ADR-008 rollout tracked here is now fulfilled on
`main` through PRs #53, #54, #55, #56, #57, #58, and #59. The sections below
remain useful as sequencing history, quality gates, and review criteria, but
they are no longer a statement that shared multi-tenant promotion is still open
 on the default branch.

For terminology and guardrails, this plan references the architecture rather than redefining it. In particular, the meaning of `installed`, `running`, and `active` comes from `ADR-009`; this plan is the source of truth for sequencing and hardening the implementation around those concepts.

## Objective

Continue hardening a runtime and configuration model that allows multiple `softwareFactoryVscode` workspaces to coexist on one host, run concurrently when desired, and evolve selected MCP services into safe multi-tenant shared services.

## Planning Assumptions

- Namespace-first install under `.copilot/softwareFactoryVscode/` is a settled architectural decision and is not revisited by this plan.
- The installed-workspace runtime contract under `.copilot/softwareFactoryVscode/` is canonical.
- Source checkout tooling may operate against the companion installed-workspace contract, but it must not define a second competing static MCP runtime contract.
- Generated host-facing files such as `software-factory.code-workspace` are projections of the installed-workspace contract rather than canonical authoring sources.

## Execution Guardrails for This Rework

- This stabilization plan MUST follow the suggested order of attack defined in `## Immediate Stabilization Rework Order` unless a failing dependency requires an earlier prerequisite fix.
- This plan MUST NOT introduce new architecture decisions or redefine accepted architecture; accepted ADRs remain authoritative per `ADR-013`.
- Accepted `ADR-008` now governs hybrid-tenancy guardrails, but this plan MUST keep rollout status honest until the required implementation and verification gates are complete.
- This rework MUST preserve the current runtime feature surface while fixing defects. Existing lifecycle commands, generated runtime artifacts, install/update/bootstrap flows, and throwaway validation flows must continue to work unless an accepted ADR already defines the current behavior as incorrect.
- This stabilization phase MUST NOT remove existing runtime features as a shortcut. Changes must be bug fixes, consistency fixes, or ADR-aligned clarifications backed by regression coverage.

## Mitigation Map and Current Resolution Status

This section answers two review questions explicitly:

1. which problems are already mitigated by the current rework,
2. and which problems are still intentionally not promoted to production behavior.

### Resolved by this rework

#### 1. Agent-bus tenant and context-packet drift

- **Status:** Resolved for the current per-workspace runtime.
- **Mitigation:** `mcp-agent-bus` now applies tenant scope consistently to checkpoints, validations, snapshots, and context-packet assembly.
- **Verification:** `tests/test_multi_tenant.py` and `tests/test_factory_install.py` cover non-default tenant context-packet behavior and wrong-tenant rejection paths.

#### 2. Workspace identity propagation drift

- **Status:** Resolved for the current runtime call path.
- **Mitigation:** FACTORY orchestrator calls now load and pass workspace identity through the shared MCP client, and runtime services fall back consistently to `PROJECT_WORKSPACE_ID` when explicit headers are absent.
- **Verification:** `tests/test_factory_install.py` and `tests/test_regression.py` cover workspace identity loading and shared MCP client tool-shape behavior.

#### 3. Bootstrap/update state-reset risk

- **Status:** Resolved for the current bootstrap refresh path.
- **Mitigation:** runtime contract refresh now preserves the recorded `runtime_state` and does not silently clear `active_workspace` during install/update/bootstrap refresh.
- **Verification:** `tests/test_factory_install.py` covers active-workspace and runtime-state preservation through bootstrap runtime sync.

#### 4. Planner and memory tool contract drift

- **Status:** Resolved for the current orchestrator path.
- **Mitigation:** the shared MCP client now exports the tool-definition format expected by the planner, and memory lesson storage uses the supported `summary` and `learnings` schema instead of unsupported arguments.
- **Verification:** `tests/test_regression.py` and `tests/test_factory_install.py` cover tool-definition export and the lesson payload contract.

#### 5. Stale tenancy architecture doublette

- **Status:** Resolved at the documentation and review-authority layer.
- **Mitigation:** the legacy duplicate ADR-007 filename is explicitly marked superseded and non-normative, the duplicate numbering is retained only for historical traceability, and the maintained architecture/plan docs now point back to the accepted ADR set rather than treating the stale draft as current truth.
- **Verification:** `tests/test_regression.py` checks the superseded ADR wording and the plan structure.

### Explicitly not resolved or promoted by this rework

#### Shared multi-tenant promotion of `mcp-memory`, `mcp-agent-bus`, and `approval-gate`

- **Status:** Not promoted in this rework.
- **Current mitigation:** keep the current runtime feature surface intact and do not treat these services as a production-ready shared control plane.
- **Reason:** `ADR-008` is accepted, but the accepted guardrails are still only partially implemented. Groundwork in code is not enough to claim rollout completion.
- **Required before promotion:** explicit tenant identity end to end, partitioned storage/logs/audit paths, cross-tenant regression coverage, shared-mode runtime verification, and operator-visible diagnostics.

## Accepted ADR to Production Rollout Path

For this codebase, an accepted ADR does not jump directly to fulfilled rollout status.

1. An accepted ADR defines the guardrails and target shape of the architecture.
2. Code may continue to ship groundwork while preserving the current runtime feature surface and keeping existing behavior stable.
3. Required migration, regression, and runtime validation must prove that the implementation satisfies the accepted rules without breaking fresh install, update-in-place, or throwaway validation flows.
4. Release notes and operator docs must describe shared-service rollout status honestly as open, advanced, or fulfilled rather than assuming that ADR acceptance equals completion.
5. Only after the rollout criteria are verified may the behavior be treated as a production-ready shared-service capability.

## Historical delivery split while shared-service rollout remained open

The execution goal during this phase was a practical working per-workspace
system for real repositories while the ADR-008 shared-service rollout was still
open. That historical sequencing remains documented here because it explains
why the practical baseline was stabilized first before shared promotion was
marked fulfilled.

| Scope | Status | Priority now | Why it matters |
| --- | --- | --- | --- |
| Practical per-workspace system for real repos | In scope now | P0 | New repositories must install, update, start, activate, verify, and recover cleanly on the isolated per-workspace path. |
| Shared multi-tenant promotion (`mcp-memory`, `mcp-agent-bus`, and `approval-gate`) | Fulfilled on default branch | Completed / historical sequencing | The accepted `ADR-008` rules, end-to-end tenant identity, partitioned storage and audit paths, cross-tenant proof, and operator-visible diagnostics are now implemented and verified on `main`. |
| Whole roadmap | Still open | After the practical baseline | The roadmap remains broader than the current isolated-path milestone because it still includes lifecycle polish, operator-facing docs and verification, and later optimization work. |

### Execution rules for the shared-service rollout program

- Do the practical per-workspace priorities first.
- Do not schedule shared multi-tenant promotion ahead of the practical baseline
  unless a non-breaking prerequisite bug fix is required to keep the current
  per-workspace runtime correct.
- Do not mark shared-service promotion as fulfilled until the practical execution plan
  below is substantially complete and the `ADR-008` rollout quality gates pass.

## Practical execution plan for a working system

The following priorities turn “make it work for real repos” into explicit
sequencing for the next implementation stretch.

### Priority 0: New repo onboarding, install, and update safety

- improve install flows so a fresh target repo gets the correct namespaced
  install, runtime metadata, generated workspace settings, and repo-local `.tmp`
  guardrails on first run;
- improve update and upgrade flows so existing installs preserve
  `runtime_state`, `active_workspace`, `.factory.env`, lock metadata, and
  generated runtime artifacts;
- harden registry refresh and recovery paths used during install, update, and
  bootstrap;
- keep throwaway validation and source-checkout companion flows aligned with the
  same contract.

#### Priority 0 definition of done

- a brand-new repo can install the factory and reach a verified per-workspace
  runtime without manual repair;
- update-in-place and bootstrap refresh behave idempotently and preserve
  operator-visible state;
- registry rebuild and reconciliation can recover from missing or stale host
  metadata without guessing wrong ownership.

#### Priority 0 validation

- focused `tests/test_factory_install.py` cases for install, update, bootstrap,
  and registry behavior;
- throwaway validation covering fresh install and update-in-place;
- repo-local `.tmp` guardrail regressions.

### Priority 1: Lifecycle truth, activation behavior, and per-workspace verification

- harden lifecycle commands (`list`, `status`, `start`, `stop`, `activate`,
  `deactivate`, `cleanup`) so they report `installed`, `running`, and `active`
  truthfully;
- make workspace activation regenerate current endpoint maps and managed
  settings deterministically;
- strengthen per-workspace verification and preflight diagnostics around
  effective ports, generated MCP URLs, and runtime reachability;
- keep operator-facing documentation aligned with the actual lifecycle surface.

#### Priority 1 definition of done

- operators can start, stop, activate, inspect, and verify one workspace
  without corrupting another workspace's state;
- activation refresh is deterministic and survives restarts;
- verification failures point to the actual effective endpoint mismatch rather
  than generic localhost assumptions.

#### Priority 1 validation

- targeted lifecycle and activation tests in `tests/test_factory_install.py`;
- `tests/test_regression.py` coverage for generated settings and doc contracts;
- runtime verification runs against non-default port assignments when relevant.

### Priority 2: Docs, regression coverage, and day-two operator confidence

- expand docs and regression coverage around install, update, lifecycle,
  verification, and new-repo onboarding;
- keep runtime guidance, handouts, and release-status communication aligned with
  the current supported baseline;
- make recovery, cleanup, and operator troubleshooting flows explicit enough for
  repeatable day-two use.

#### Priority 2 definition of done

- the practical per-workspace path is described clearly enough that a new repo
  owner can onboard and recover without reverse-engineering chat history;
- the regression suite protects the key install, update, lifecycle, and
  verification contracts from silent drift.

#### Priority 2 validation

- `tests/test_regression.py` plus the shell integration regression;
- focused documentation regressions for plan, release-note, and onboarding
  contracts;
- fresh-install and update-in-place reruns when lifecycle or verification docs
  change.

### Shared multi-tenant rollout completion note

- the ADR-008 promotion gate is now fulfilled on the default branch;
- the practical per-workspace baseline remains the default supported operator
  path even though shared mode is now fully defensible and verified; and
- future work may keep hardening or optimizing shared mode, but it no longer
  blocks truthful `fulfilled` release/operator wording.

## Current Baseline

- The host-scoped workspace registry, per-workspace port allocation, generated runtime manifest, and generated workspace MCP URLs already exist in the codebase.
- Lifecycle commands already exist through `scripts/factory_stack.py` (`list`, `status`, `start`, `stop`, `activate`, `deactivate`, `cleanup`).
- The remaining purpose of this plan is to sequence hardening, documentation cleanup, and future tenancy work rather than to re-decide namespace placement.

## ADR-008 rollout mitigation program

Accepting `ADR-008` made the hybrid-tenancy rules normative architecture. It did **not** by itself complete the shared-service rollout. The tracks below defined the remaining work required before release notes or operator docs could describe shared multi-tenant promotion as fulfilled, and they are now complete on the default branch.

### Track 1: Promotion boundary and shared-mode contract

- define exactly what counts as candidate-shared groundwork, shared-mode rollout in progress, and fulfilled shared-service promotion;
- document the runtime topology and compatibility boundary between the current per-workspace path and any promoted shared mode.

#### Track 1 definition of done

- architecture, plan, install, and release docs describe shared-service status using the same vocabulary;
- candidate-shared groundwork is clearly distinguished from fulfilled shared-mode rollout;
- release status tables can state whether the rollout is open, advanced, or fulfilled without ambiguity.

#### Track 1 quality checks

- `tests/test_regression.py` locks the shared-service rollout wording across ADR, plan, install, tests README, and release template;
- manual doc review confirms no operator-facing file claims rollout completion prematurely.

### Track 2: Strict tenant identity enforcement

- require explicit tenant identity for promoted shared mode across `mcp-memory`, `mcp-agent-bus`, and `approval-gate`;
- retain compatibility fallback behavior only where the per-workspace runtime explicitly depends on it;
- reject ambiguous or mismatched tenant requests in promoted shared mode.

#### Track 2 definition of done

- the shared-service request contract distinguishes per-workspace compatibility mode from promoted shared mode;
- promoted shared mode rejects missing tenant identity rather than silently falling back;
- tenant identity is propagated end to end through clients and services.

#### Track 2 quality checks

- add unit/integration tests for missing-header rejection, mismatched-header rejection, and successful explicit-header flows;
- add regression coverage for shared MCP client propagation of `X-Workspace-ID` across all promoted services.

### Track 3: Explicit shared-service topology and lifecycle

- define how shared services are launched, discovered, and reported when they are no longer treated as merely candidate-shared;
- ensure lifecycle helpers and runtime metadata expose whether services are per-workspace or shared.

#### Track 3 definition of done

- compose/runtime metadata defines whether memory, agent bus, and approval gate are running in shared or per-workspace mode;
- `preflight`, `status`, and runtime verification report the topology truthfully;
- promoted shared services are not accidentally duplicated per workspace in shared mode.

#### Track 3 quality checks

- targeted lifecycle tests confirm truthful status reporting for shared versus per-workspace topology;
- Docker-backed validation confirms that shared services and workspace-scoped services are launched as intended.

### Track 4: Partitioned storage, logs, and audit paths

- ensure all persistent reads/writes, logs, metrics, and audit trails are partitioned or labeled by tenant identity;
- keep destructive admin actions tenant-safe.

#### Track 4 definition of done

- every persistent read/write path in memory and agent bus is scoped by tenant identity;
- audit/log surfaces for promoted shared services either store data per tenant path or attach tenant identity to each record;
- purge or admin actions cannot remove another tenant's data.

#### Track 4 quality checks

- expand store/bus tests to cover tenant-scoped purge and wrong-tenant rejection paths;
- add service-level checks or diagnostics proving tenant-labeled audit/log behavior.

### Track 5: Operator-visible diagnostics and runtime verification

- expose enough runtime truth that an operator can tell whether shared mode is healthy, misconfigured, or leaking tenant context;
- extend verification helpers to probe shared-mode expectations.

#### Track 5 definition of done

- `verify_factory_install.py` and `factory_stack.py preflight/status` surface tenant-identity and shared-mode drift clearly;
- operator docs explain how to diagnose missing tenant identity, mismatched tenants, and shared-mode rollout state;
- runtime smoke prompts cover shared-mode checks when applicable.

#### Track 5 quality checks

- add regression tests for shared-mode verification and preflight output;
- run runtime verification against a non-default/shared configuration and confirm actionable error messages.

### Track 6: Cross-tenant end-to-end isolation proof

- prove that promoted shared services do not leak memory, bus state, approval state, or diagnostics across tenants;
- prove that approval flows remain tenant-safe.

#### Track 6 definition of done

- end-to-end tests show that two tenants cannot read or mutate each other's memory, bus runs, pending approvals, or plan cards;
- approval and rejection operations fail explicitly for the wrong tenant;
- at least one Docker-backed scenario exercises more than one tenant/workspace against the rollout path.

#### Track 6 quality checks

- extend `tests/test_multi_tenant.py` with service-boundary scenarios;
- add targeted approval-gate integration coverage;
- run `RUN_DOCKER_E2E=1 pytest tests/test_throwaway_runtime_docker.py -v -s` or equivalent shared-mode validation.

### Track 7: Release, operator docs, and regression promotion

- move operator docs and release communications from “blocked ADR” wording to “accepted architecture, rollout open” wording first, then to truthful fulfilled wording once every rollout track is complete;
- keep the per-workspace baseline explicit even after shared promotion becomes fulfilled.

#### Track 7 definition of done

- release template, install guide, tests README, handout, cheat sheet, and architecture docs now reflect that the ADR-008 promotion gate is fulfilled while the practical per-workspace baseline remains the default supported path;
- regression tests fail if docs drift back into either stale “rollout open” language or unsupported claims that ignore the practical baseline.

#### Track 7 quality checks

- `tests/test_regression.py` covers the wording shift and the accepted/open distinction;
- release note dry runs use the updated template language successfully.

### Track 8: Final promotion gate

- mark shared-service rollout as fulfilled only when the prior tracks are complete and the rollout can be defended in code, tests, and release notes.

#### Track 8 definition of done

- all prior rollout tracks are complete;
- release notes can honestly mark shared multi-tenant promotion as fulfilled without contradicting code or diagnostics;
- operator guidance for shared mode is complete enough for repeatable day-two use.

#### Track 8 quality checks

- run the mandatory regression suite for docs, tenancy, lifecycle, and Docker-backed validation;
- perform a final architecture/documentation review before any release claims fulfilled shared-service promotion.

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
- persisted port variables in `.copilot/softwareFactoryVscode/.factory.env`,
- generated workspace MCP URLs,
- generated health endpoint map.

### Workstream 2 Detailed Steps

1. Define canonical offsets for all published services.
2. Add allocator that:
   - prefers deterministic allocation,
   - verifies host-port availability,
   - retries safely when a block is unavailable.
3. Write effective port values into `.copilot/softwareFactoryVscode/.factory.env` during install/update or activation.
4. Replace hardcoded MCP URLs in generated workspace settings with URLs derived from the effective ports.
5. Extend runtime verification to probe those generated URLs and effective health ports.

### Workstream 2 Robustness Checks

- verification must fail with clear diagnostics when a required port is missing or inconsistent,
- regenerated settings must be deterministic and idempotent,
- compose and workspace settings must not drift.

## Workstream 3: Active Workspace Operations

### Workstream 3 Deliverables

- operator commands to list/start/stop/activate/deactivate workspaces,
- clear distinction between installed, running, and active states as defined by `ADR-009`,
- compatibility with throwaway validation.

### Workstream 3 Detailed Steps

1. Add commands such as:
   - `factory_stack.py list`,
   - `factory_stack.py status`,
   - `factory_stack.py activate`,
   - `factory_stack.py stop`,
   - `factory_stack.py cleanup`.
2. Make activation regenerate workspace settings and ensure the runtime endpoint map is current.
3. Make stop/cleanup update registry state.
4. Update throwaway validation to use the same lifecycle manager rather than ad hoc start/stop sequencing.

### Workstream 3 Robustness Checks

- active status must survive process restarts,
- stopping one workspace must not corrupt another workspace registry record,
- cleanup must clearly separate container removal from image pruning.

## Workstream 4: Hybrid Tenancy Classification

**Execution status:** active gated rollout track. Complete only after the
practical per-workspace execution plan above is stable enough to support real
repo onboarding, install and update safety, lifecycle truth, and per-workspace
verification.

### Workstream 4 Deliverables

- service classification matrix,
- shared-service tenant contract,
- migration plan for candidate shared services,
- rollout gates tracked through the ADR-008 mitigation program.

### Workstream 4 Detailed Steps

1. Mark current services as either:
   - workspace-scoped single-tenant,
   - or candidate shared multi-tenant.
2. Freeze workspace-scoped services behind the `/target` isolation rule until redesigned.
3. Define shared-service request contract using explicit tenant identity in headers or equivalent transport metadata.
4. Define storage partition rules for shared services.
5. Add cross-tenant regression tests before any shared-service rollout.
6. Align runtime diagnostics and verification with the chosen shared-mode topology.
7. Update operator/release docs only after the rollout gates for this workstream are satisfied.

### Workstream 4 Robustness Checks

- no shared service can read or write data without a tenant identity,
- no tenant can observe another tenant’s logs or records by default.
- runtime diagnostics must surface shared-mode drift and tenant mismatches clearly.

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

- `.copilot/softwareFactoryVscode/.factory.env` port projection,
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

Phase D remains blocked until the practical per-workspace execution priorities
are substantially complete and the `ADR-008` rollout quality gates are satisfied.

## Recommended Order of Implementation

1. workspace identity and registry,
2. port allocation and generated settings,
3. verification and lifecycle commands,
4. throwaway/runtime workflow integration,
5. multi-tenant shared-service rollout (only after the practical
   per-workspace priorities above are substantially complete and the `ADR-008`
   rollout quality gates are ready to prove).

## Immediate Stabilization Rework Order

The current codebase now needs a focused stabilization pass before any further shared-service promotion work.

### 1. Fix tenant and context correctness in `mcp-agent-bus`

- Make checkpoint, snapshot, validation, and context-packet reads consistently respect `project_id`.
- Ensure tool-layer method signatures and backend method signatures match.
- Treat tenant-scoped reads/writes as current-runtime correctness, not future optional hardening.

#### Agent-bus definition of done

- `bus_write_checkpoint`, `bus_write_snapshot`, `bus_write_validation`, and `bus_read_context_packet` all preserve tenant scope correctly.
- A non-default workspace receives its own plan, snapshots, validations, and checkpoints through the context packet.
- Wrong-tenant writes fail explicitly instead of silently writing to the wrong logical scope.

#### Agent-bus quality checks

- Add unit tests for non-default `project_id` reads and writes.
- Add regression coverage for context-packet completeness outside the `default` tenant.

### 2. Standardize workspace identity propagation across runtime clients and services

- Pass `X-Workspace-ID` from orchestrator/MCP client calls when a workspace identity is known.
- Normalize service fallback behavior so per-workspace runtimes use `PROJECT_WORKSPACE_ID` consistently when explicit headers are absent.
- Do not mark shared-service rollout fulfilled until explicit tenant identity is proven end to end.

#### Workspace identity definition of done

- FACTORY orchestrator clients include workspace identity when the installed runtime contract provides one.
- `mcp-memory`, `mcp-agent-bus`, and `approval-gate` resolve the same effective workspace identity in per-workspace mode.
- Missing-header behavior is consistent and documented.

#### Workspace identity quality checks

- Add tests for workspace identity loading from generated runtime metadata.
- Add regression tests for service fallback behavior against `PROJECT_WORKSPACE_ID`.

### 3. Preserve operator-visible state during bootstrap, refresh, update, and upgrade flows

- Bootstrap/update must not clear the active workspace selection as an unintended side effect.
- Bootstrap/update must preserve the current runtime state metadata unless the lifecycle manager has already changed it intentionally.
- Migration-safe refresh must work from both the installed checkout and the source checkout using the companion runtime contract.

#### Bootstrap and update definition of done

- Refreshing runtime artifacts does not clear `active_workspace` in the host registry.
- Update/install flows preserve or intentionally transition runtime state without surprise resets.
- Existing installs can be refreshed without reintroducing root-level legacy artifacts or losing generated runtime metadata.

#### Bootstrap and update quality checks

- Add regression tests covering active-workspace preservation through bootstrap/update.
- Re-run install/update and throwaway validation scenarios after the changes.

### 4. Repair planner and memory tool contract drift

- Make the MCP client expose the tool-definition shape the planner expects.
- Make lesson storage call `memory_store_lesson` using the actual supported schema.
- Remove silent degradation paths where possible or at least cover them with explicit tests.

#### Planner and memory definition of done

- Planner tool enumeration works through the shared MCP client API.
- Lesson storage uses `summary` and `learnings` instead of unsupported arguments.
- The orchestrator path no longer depends on broad exception swallowing to stay green.

#### Planner and memory quality checks

- Add unit tests for MCP client tool definition export.
- Add regression tests that verify the lesson payload matches the memory tool schema.

### 5. Retire stale architecture doublettes before further rework

- Mark the legacy duplicate tenancy ADR as superseded and point to the current authoritative ADR set.
- Ensure plan/synthesis docs do not treat proposed tenancy rules as already accepted architecture.

#### Documentation definition of done

- There is no remaining document that looks like an accepted competing source of truth for tenancy or lifecycle semantics.
- `ADR-013` authority rules are reflected consistently across architecture and plan docs.

#### Documentation quality checks

- Add regression checks that the superseded ADR is explicitly marked historical/non-normative.
- Re-run doc regression tests after the edits.

### 6. Expand regression coverage around the real FACTORY pipeline

- Add tests for planner/orchestrator support surfaces that currently drift silently.
- Extend migration coverage to install/update/bootstrap/throwaway flows touched by this rework.

#### Regression definition of done

- The bugs fixed in this rework are each covered by a regression test.
- The targeted suite catches tenant-scoping drift, workspace identity drift, bootstrap state drift, and planner/memory contract drift.

#### Regression quality checks

- Run focused tests for `test_multi_tenant.py`, `test_regression.py`, and targeted `test_factory_install.py` cases.
- Re-run update/throwaway validation scenarios relevant to lifecycle and migration safety.

## Program-level definition of done

This stabilization rework is complete only when all of the following are true:

- current lifecycle and registry semantics remain aligned with accepted ADRs,
- install/update/bootstrap flows preserve operator-visible state and generated runtime artifacts correctly,
- FACTORY runtime calls propagate workspace identity consistently,
- agent-bus context packets are tenant-correct for non-default workspaces,
- planner and lesson-storage integrations use supported MCP contracts,
- doc authority is unambiguous and the stale tenancy doublette is retired,
- focused regression and migration validation suites pass.

## Mandatory quality gates for this rework

Before considering this rework complete, run at minimum:

1. `tests/test_multi_tenant.py`
2. `tests/test_regression.py`
3. focused `tests/test_factory_install.py` cases for:
   - activation refresh,
   - bootstrap/update state preservation,
   - update/install compatibility,
   - registry reconciliation.
4. targeted throwaway validation coverage in `tests/test_throwaway_runtime_docker.py` or the equivalent validation driver when Docker-backed tests are intentionally enabled.

## Transition, update, and upgrade safety rules

- Update/install/bootstrap changes must remain idempotent for existing installed workspaces.
- Refreshing generated runtime artifacts must not silently demote an active workspace to inactive.
- Migration-safe updates must preserve `.factory.env`, `lock.json`, generated runtime metadata, and managed workspace settings unless an explicit lifecycle command intentionally changes them.
- Runtime cleanup semantics from `ADR-010` remain authoritative and must not be weakened by this rework.
- New runtime behavior must be validated against both fresh-install and update-in-place paths.

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
