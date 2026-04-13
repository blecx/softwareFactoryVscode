# Multi-Workspace and Multi-Tenant MCP Implementation Plan

## Status

Proposed

This document is a sequencing plan, not the normative source of architecture truth. Per `ADR-013`, accepted ADRs define architecture guardrails and terminology, architecture synthesis documents may explain but not override them, and plans remain authoritative only for sequencing and hardening work. Accepted runtime contracts now live in `ADR-012`, `ADR-007`, `ADR-009`, and `ADR-010`. Hybrid-tenancy promotion rules are currently proposed in `ADR-008`; they do not become accepted architecture or production rollout criteria until that ADR is accepted and the code satisfies it. `MULTI-WORKSPACE-MCP-ARCHITECTURE.md` is a maintained architecture synthesis that explains how those decisions fit together and maps them onto the current codebase. When this plan or that synthesis lags, the accepted ADRs and verified code are the source of truth.

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
- Proposed ADRs (including `ADR-008`) MUST NOT be treated as accepted rollout criteria until they are formally accepted.
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
- **Mitigation:** the legacy duplicate ADR is explicitly marked superseded and non-normative, and the maintained architecture/plan docs now point back to the accepted ADR set rather than treating the stale draft as current truth.
- **Verification:** `tests/test_regression.py` checks the superseded ADR wording and the plan structure.

### Explicitly not resolved or promoted by this rework

#### Shared multi-tenant promotion of `mcp-memory`, `mcp-agent-bus`, and `approval-gate`

- **Status:** Not promoted in this rework.
- **Current mitigation:** keep the current runtime feature surface intact and do not treat these services as a production-ready shared control plane.
- **Reason:** `ADR-008` is still `Proposed`, and the accepted architecture hierarchy in `ADR-013` does not allow a proposed ADR to become production truth merely because some groundwork exists in code.
- **Required before promotion:** accepted ADR status, explicit tenant identity end to end, partitioned storage/logs/audit paths, cross-tenant regression coverage, and operator-visible diagnostics.

## Proposed ADR to Production Promotion Path

For this codebase, a proposed ADR does not jump directly to production behavior.

1. A `Proposed` ADR defines candidate rules and review intent, not production rollout authority.
2. Code may add non-breaking groundwork while preserving the current runtime feature surface and keeping existing behavior stable.
3. Required migration, regression, and runtime validation must prove that the implementation satisfies the proposed rules without breaking fresh install, update-in-place, or throwaway validation flows.
4. The ADR must then move from `Proposed` to `Accepted` through explicit document review and update.
5. Only after that acceptance step may the behavior be treated as production rollout criteria or as a production-ready shared-service capability.

## Practical delivery split while shared-service promotion remains blocked

The current execution goal is a practical working per-workspace system for real
repositories. Shared multi-tenant promotion remains blocked as a later
optimization and rollout step; it is not the current prerequisite for making
new installs, updates, lifecycle commands, and verification trustworthy.

| Scope | Status | Priority now | Why it matters |
| --- | --- | --- | --- |
| Practical per-workspace system for real repos | In scope now | P0 | New repositories must install, update, start, activate, verify, and recover cleanly on the isolated per-workspace path. |
| Shared multi-tenant promotion (`mcp-memory`, `mcp-agent-bus`, and `approval-gate`) | Blocked for now | Deferred / last major promotion step | This is mainly a later efficiency and shared-control-plane optimization, and it remains gated by `ADR-008`, end-to-end tenant identity, partitioned storage and audit paths, cross-tenant proof, and operator-visible diagnostics. |
| Whole roadmap | Still open | After the practical baseline | The roadmap remains broader than the current isolated-path milestone because it still includes lifecycle polish, operator-facing docs and verification, and any later approved shared-service promotion. |

### Execution rules for the blocked shared-service phase

- Do the practical per-workspace priorities first.
- Do not schedule shared multi-tenant promotion ahead of the practical baseline
   unless a non-breaking prerequisite bug fix is required to keep the current
   per-workspace runtime correct.
- Treat shared-service promotion as blocked until the practical execution plan
   below is substantially complete and `ADR-008` has moved to `Accepted`.

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

### Deferred phase: Shared multi-tenant promotion remains blocked

- do not treat shared multi-tenant promotion as the current delivery target;
- revisit it only after Priorities 0 through 2 are stable enough for real repo
   onboarding and per-workspace operations;
- require accepted ADR status, explicit tenant identity end to end, partitioned
   storage and audit paths, cross-tenant regression coverage, and operator
   diagnostics before unblocking it.

## Current Baseline

- The host-scoped workspace registry, per-workspace port allocation, generated runtime manifest, and generated workspace MCP URLs already exist in the codebase.
- Lifecycle commands already exist through `scripts/factory_stack.py` (`list`, `status`, `start`, `stop`, `activate`, `deactivate`, `cleanup`).
- The remaining purpose of this plan is to sequence hardening, documentation cleanup, and future tenancy work rather than to re-decide namespace placement.

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

**Execution status:** blocked for the current delivery cycle. Revisit only
after the practical per-workspace execution plan above is complete enough to
support real repo onboarding, install and update safety, lifecycle truth, and
per-workspace verification.

### Workstream 4 Deliverables

- service classification matrix,
- shared-service tenant contract,
- migration plan for candidate shared services.

### Workstream 4 Detailed Steps

1. Mark current services as either:
   - workspace-scoped single-tenant,
   - or candidate shared multi-tenant.
2. Freeze workspace-scoped services behind the `/target` isolation rule until redesigned.
3. Define shared-service request contract using explicit tenant identity in headers or equivalent transport metadata.
4. Define storage partition rules for shared services.
5. Add cross-tenant regression tests before any shared-service rollout.

### Workstream 4 Robustness Checks

- no shared service can read or write data without a tenant identity,
- no tenant can observe another tenant’s logs or records by default.

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
are substantially complete and `ADR-008` has moved to `Accepted`.

## Recommended Order of Implementation

1. workspace identity and registry,
2. port allocation and generated settings,
3. verification and lifecycle commands,
4. throwaway/runtime workflow integration,
5. multi-tenant shared-service promotion (blocked until the practical
   per-workspace priorities above are substantially complete and `ADR-008` is
   accepted).

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
- Keep shared-service promotion blocked until explicit tenant identity is proven end to end.

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
