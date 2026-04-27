# Changelog

All notable changes to **Software Factory for VS Code** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Unreleased Summary

No unreleased changes recorded yet after `2.6`.

## [2.6] — 2026-04-27

### Summary for 2.6

Release 2.6 is a production-readiness and quota-governance release built on
the fulfilled 2.5 shared-service baseline. The factory now has a bounded MCP
runtime manager contract for lifecycle-sensitive operations, an internal
production gate that bundles blocking Docker build parity with promoted runtime
recovery proof, and a supported day-two operator surface for backup, restore,
diagnostics, and incident response. The release also adds provider-aware quota
governance with workspace-global coordination, fairness feedback, and load
validation, while splitting production CI into diagnosable groups without
weakening the aggregate sign-off path.

### Added in 2.6

- **MCP runtime manager contract** — `factory_runtime/mcp_runtime/` plus
  related `scripts/factory_stack.py`, verification, and workflow updates now
  provide a single runtime snapshot, bounded suspend/resume semantics, repair
  flows, and cleanup parity for lifecycle-sensitive operations.
- **Internal production readiness surface** — the repo now ships a fail-closed
  internal production mode, blocking Docker build parity, promoted Docker E2E
  runtime proofs, supported backup/restore commands, machine-readable runtime
  diagnostics, and incident-response/day-two operator runbooks.
- **Quota governance stack** — provider-aware quota policy, workspace-global
  coordination, limiter telemetry, hierarchical budget definitions,
  admission-control leasing, requester-lineage fairness, and load validation
  now give the LLM/request path an explicit governed budget contract.
- **Diagnosable production CI groups** — production parity can now run as
  `docs-contract`, `docker-builds`, and `runtime-proofs` slices while the
  canonical aggregate `--mode production` gate remains the final readiness
  authority.

### Fixed in 2.6

- **Runtime backup/restore truth** — WAL-backed restore bundles, host-writable
  runtime data, SQLite bind mounts, runtime permissions, and throwaway parity
  collisions are now handled consistently enough for repeatable recovery proof.
- **Production parity/reporting sharp edges** — CI naming, local-vs-GitHub
  parity messaging, and temporary-file handling are now clearer and less
  failure-prone for operators and automation.
- **Architecture reference drift** — ADR-014 acceptance and ADR-007 discovery
  guidance now point reviewers and agents at the correct authority sources.

### Changed in 2.6

- **Production-readiness sign-off** — `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`
  is now the canonical internal production gate, and the CI workflow exposes
  the same gate through diagnosable component jobs plus the final aggregate
  readiness lane.
- **Runtime lifecycle discipline** — status, preflight, verification,
  activate/deactivate, suspend/resume, and repair flows now rely on one
  bounded runtime-manager contract instead of loosely coordinated checks.
- **Post-promotion focus** — shared multi-tenant promotion remains fulfilled on
  `main`; this release shifts the roadmap emphasis toward runtime operations,
  recovery evidence, and quota governance rather than reopening the already
  closed promotion claim.

### Operational Notes for 2.6

- The default supported operator path remains the namespace-first,
  per-workspace runtime opened via `software-factory.code-workspace`.
- Shared multi-tenant promotion for `mcp-memory`, `mcp-agent-bus`, and
  `approval-gate` stays fulfilled on `main`; 2.6 hardens the surrounding
  runtime, production, and quota-governance surfaces.
- The canonical local production sign-off is
  `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`.
- Standard `./.venv/bin/python ./scripts/local_ci_parity.py` runs still skip
  Docker image builds by default and report that boundary as a warning.
- Supported day-two operations now include backup/restore proof, incident
  response guidance, and machine-readable diagnostics instead of relying on
  ad-hoc recovery steps.
- Release validation for 2.6 passed through three consecutive
  `./.venv/bin/python ./scripts/local_ci_parity.py --mode production` runs
  (`current_green_streak=3/3`, `final_signoff=ready`) plus the post-commit
  `scripts/verify_release_docs.py` and
  `scripts/factory_release.py write-manifest --check` guardrails.

## [2.5] — 2026-04-20

### Summary for 2.5

Release 2.5 closes the `ADR-008` shared-service promotion gate on `main`,
hardens the day-two operator workflow, and refreshes the user-facing
documentation for modern VS Code. The repository can now honestly describe
`mcp-memory`, `mcp-agent-bus`, and `approval-gate` as fulfilled shared
multi-tenant control-plane services on the default branch, while the practical
per-workspace runtime remains the default supported operator path. The release
also aligns README/operator docs with VS Code `1.116+`, where GitHub Copilot
ships built in, and clarifies that older releases still need the GitHub
Copilot extension while GitHub Pull Requests and Issues remains optional.

### Added in 2.5

- **Ordered issue queue guardrail** — `.github/hooks/github-issue-queue-guard.json`
  and `scripts/github_issue_queue_guard.py` now require GitHub-truth
  checkpoints in `.tmp/github-issue-queue-state.md` before unsafe
  continue/merge/close flows.
- **Interruption recovery workflow** — `scripts/capture_recovery_snapshot.py`,
  `.github/prompts/resume-after-interruption.prompt.md`, and the matching skill
  now create `.tmp/interruption-recovery-snapshot.md` with optional runtime
  status.
- **Execution-surface guard** — `scripts/workspace_surface_guard.py` and
  updated VS Code tasks now route workspace-sensitive verify/update/runtime
  flows through the generated-workspace contract instead of inventing a second
  source-checkout runtime surface.
- **Non-interactive GitHub helper** — `scripts/noninteractive_gh.py` plus
  updated workflow docs and skills now provide safe issue/PR listing and
  PR-check handling without hanging interactive terminals.
- **Version-aware VS Code onboarding guidance** — `README.md`, `docs/INSTALL.md`,
  `docs/HANDOUT.md`, and `docs/CHEAT_SHEET.md` now distinguish VS Code
  `1.116+` built-in Copilot from older releases that still require the
  extension, and they mark GitHub Pull Requests and Issues as optional.
- **Todo-app regression contract** — `scripts/todo_app_regression.py` and new
  tests add a reusable throwaway runtime regression surface for end-to-end
  checks.

### Fixed in 2.5

- **Shared-mode tenant identity enforcement** — `mcp-memory`, `mcp-agent-bus`,
  and `approval-gate` now reject ambiguous or mismatched tenant requests in
  promoted shared mode while keeping explicit per-workspace compatibility paths
  honest.
- **Shared-service topology truth** — `scripts/factory_stack.py`,
  `scripts/verify_factory_install.py`, and `scripts/factory_workspace.py` now
  report shared versus per-workspace ownership and effective discovery URLs
  truthfully through `preflight`, `status`, activation, and verification.
- **Tenant-partitioned persistence and audit scope** — memory and agent-bus
  storage now persist tenant identity on shared rows, label audit evidence by
  tenant, and keep destructive admin/purge paths tenant-safe.
- **Docker service-name FastMCP handshake** — shared FastMCP services now pass
  the bind host into the constructor so Docker service-name `Host` headers are
  no longer rejected by localhost-only validation.
- **Local CI parity reporting** — `scripts/local_ci_parity.py` now reports
  actionable findings and improvement plans instead of collapsing multiple
  precheck failures into opaque output.

### Changed in 2.5

- **`ADR-008` rollout status language** — operator docs, architecture docs,
  tests, and the release template now treat shared multi-tenant promotion as
  fulfilled on `main` while keeping the practical per-workspace baseline as the
  default supported operator path.
- **Workflow hardening program closeout** — `docs/WORK-ISSUE-WORKFLOW.md`,
  `docs/CHAT-SESSION-TROUBLESHOOTING-REPORT.md`, prompts, skills, and tasks now
  align around ordered issue checkpoints, interruption recovery,
  non-interactive GitHub flows, and execution-surface discipline.
- **Editor onboarding contract** — repo docs now tie Copilot setup expectations
  to VS Code version, GitHub sign-in, and optional PR tooling instead of
  treating the Copilot extension as universally required.
- **Regression depth** — expanded multi-tenant, install/runtime, workflow, and
  documentation tests now lock the promoted shared-service contract and the
  operator guardrails that support it.

### Operational Notes for 2.5

- The default supported operator path remains the namespace-first,
  per-workspace runtime opened via `software-factory.code-workspace`.
- Shared multi-tenant promotion is now fulfilled on the default branch for
  `mcp-memory`, `mcp-agent-bus`, and `approval-gate`; future hardening can
  continue without pretending the rollout is still open.
- VS Code `1.116+` no longer needs a manual GitHub Copilot extension install
  for the documented AI workflow, but older VS Code releases still do.
- GitHub Pull Requests and Issues remains optional operator tooling rather than
  a prerequisite for Copilot chat, inline suggestions, or agents.
- Ordered issue progression, interruption recovery, and wrong-surface
  prevention are now first-class workflow guardrails rather than informal chat
  habits.
- Release validation for 2.5 passed in the current repo state: Black, Flake8,
  isort, `pytest tests/` (`211 passed, 2 skipped`),
  `./tests/run-integration-test.sh`, and release-manifest parity.

## [2.4] — 2026-04-13

### Summary for 2.4

Release 2.4 is a stabilization release for the current namespace-first,
per-workspace runtime. The immediate hardening pass around workspace identity,
tenant-scoped runtime behavior, bootstrap/update state preservation, and
planner/memory contract correctness is now complete enough to ship as the new
baseline. At the same time, the release keeps the architecture honest:
candidate shared services are still not promoted to a production shared control
plane, and the broader multi-tenant roadmap remains open.

### Added in 2.4

- **Planner-facing MCP tool definitions** — `factory_runtime/agents/mcp_client.py`
  now exports OpenAI-compatible tool definitions so the planner can enumerate
  tools through the shared client without relying on missing API surface.
- **Regression coverage for the stabilization pass** — new and expanded tests now
  cover non-default tenant context packets, cross-tenant bus write rejection,
  workspace identity loading, lesson payload schema conformance, bootstrap state
  preservation, and the mitigation-plan/superseded-ADR documentation contract.
- **Repo-local throwaway testing guardrail** — `scripts/validate_throwaway_install.py`
  now keeps default throwaway install/runtime validation inside the source
  repository's gitignored `.tmp/throwaway-targets/` area unless an operator
  explicitly opts into an external target.

### Fixed in 2.4

- **Agent-bus tenant scoping** — `factory_runtime/apps/mcp/agent_bus/bus.py` and
  `factory_runtime/apps/mcp/agent_bus/mcp_server.py` now apply tenant scope
  consistently to checkpoints, validations, snapshots, and context-packet
  assembly, and they reject wrong-tenant writes explicitly.
- **Workspace identity propagation** — `factory_runtime/agents/factory.py`,
  `factory_runtime/apps/mcp/memory/mcp_server.py`, and
  `factory_runtime/apps/approval_gate/main.py` now resolve and carry the same
  effective workspace identity through the current runtime path.
- **Bootstrap/update state preservation** — `scripts/bootstrap_host.py` now keeps
  recorded `runtime_state` and does not silently clear `active_workspace` while
  refreshing runtime artifacts during install/update/bootstrap.
- **Lesson storage contract drift** — the FACTORY orchestrator now stores
  `memory_store_lesson` records using the supported `summary` and `learnings`
  schema instead of unsupported payload fields.
- **Stale architecture authority drift** — the legacy duplicate multi-workspace
  ADR is now explicitly superseded and non-normative, and the maintained
  architecture/plan docs now distinguish what is resolved by the per-workspace
  rework versus what remains intentionally unpromoted.

### Changed in 2.4

- **Practical interpretation of plan status** — the current per-workspace runtime
  hardening pass is treated as fulfilled enough for release, while shared
  multi-tenant runtime promotion remains open and the full roadmap exit
  condition is still not complete.
- **Shell integration regression guardrail** — `tests/run-integration-test.sh`
  now stages its mock host under repo-local `.tmp/integration-test/`, cleans it
  up on exit, and excludes `.tmp` from the copied snapshot so the integration
  regression follows the same in-workspace testing boundary as throwaway
  install/runtime validation.

### Operational Notes for 2.4

- This release marks the current **per-workspace runtime hardening** as the new
  baseline.
- Shared multi-tenant promotion for `mcp-memory`, `mcp-agent-bus`, and
  `approval-gate` remains intentionally blocked until the `ADR-008` promotion
  path is accepted and fully validated.
- Default disposable validation now stays inside repo-local, gitignored `.tmp`
  paths, reducing the risk of accidental breakout into unrelated directories.
- A real repo-local throwaway flow was re-run for this release: install older
  commit → detect update → apply update → re-verify runtime compliance.
- Full regression coverage and the shell integration regression both passed on
  the 2.4 state.

## [2.3] — 2026-04-10

### Summary for 2.3

Release 2.3 is a functional enhancement release focused on making Software
Factory upgrades first-class citizens. The repo now publishes structured release
metadata, every install carries the release/build identity needed for update
decisions, and installed workspaces get a built-in updater that can compare
against the canonical source repository or GitHub-hosted release manifest.

### Added in 2.3

- **Runtime preflight workflow** — `scripts/factory_stack.py preflight`, matching
  VS Code task wiring, and updated install guidance now validate service
  inventory, expected host ports, runtime manifest alignment, and generated
  workspace MCP URLs before live probes run.
- **Release bump policy enforcement** — CI now requires `CHANGELOG.md`,
  `.github/releases/v<version>.md`, and `manifests/release-manifest.json` to be
  updated whenever `VERSION` changes, so release-number bumps cannot ship
  without the corresponding human and machine-readable metadata.
- **Structured release lifecycle metadata** — installs now stamp structured
  release/build information into `lock.json` and `runtime-manifest.json`, and
  the repo now carries `manifests/release-manifest.json` as the machine-readable
  source of truth for update checks.
- **Installed updater entrypoint** — `scripts/factory_update.py` now lets any
  installed workspace check/apply updates against the configured source repo,
  including GitHub-hosted origins.
- **Update regression coverage** — `tests/test_factory_install.py` now covers
  dirty installed checkouts that trigger updater-created `local-backup-*`
  branches during refresh, and verifies that release metadata is preserved.

### Fixed in 2.3

- **Namespace-first upgrade drift detection** — `scripts/verify_factory_install.py`
  now fails when legacy hidden-tree artifacts or stale legacy `.gitignore`
  entries remain after upgrade, including partial leftovers.
- **Generated workspace refresh** — `scripts/bootstrap_host.py` now safely
  refreshes factory-managed workspace sections in place, updates stale MCP URLs,
  removes legacy `.gitignore` blocks, and preserves existing lock metadata when
  bootstrap is re-run standalone.
- **Reopen/restart port stability** — `scripts/factory_workspace.py` now
  preserves persisted workspace port assignments across restored workspaces
  instead of reallocating a fresh port block.
- **Repo-fundamentals MCP URL mapping** — generated MCP URLs and preflight port
  validation now match the actual compose host-port contract for `git-mcp`,
  `search-mcp`, and `filesystem-mcp`.
- **Dirty install updates** — `scripts/install_factory.py` now keeps the original
  target branch when a dirty installed checkout is backed up, instead of getting
  stranded on a temporary `local-backup-*` branch.
- **Release metadata on update** — install updates now restamp `lock.json.version`
  from the checked-in `VERSION` file so upgraded installs continue to record the
  release version (`2.3`) instead of a branch label like `main`.

### Release Notes

- Every install now ships with `scripts/factory_update.py` for consistent
  `check` / `apply` update workflows.
- `manifests/release-manifest.json` is now the machine-readable source of truth
  for release comparison and GitHub-backed update checks.
- Release-number bumps are now guarded in CI and mirrored in AI instructions so
  changelog and GitHub release notes stay in lockstep with `VERSION`.
- A final strict smoke rerun for `release_update_smoke_flow` and
  `verify_release_docs` passed cleanly under `pytest -x -W error`, confirming
  the new release/update contract is warning-clean.
- Runtime manifests, lock metadata, CI validation, VS Code tasks, and install
  guidance now align around the same release/update contract.

## [2.2] — 2026-04-10

### Release Summary

Release 2.2 is a validation-hardening release focused on making the factory more
truthful under end-to-end install/runtime checks and stricter regression modes.
The release closes the gap between “tests are green” and “a fresh throwaway
install actually boots, verifies, and cleans up correctly.”

- **Throwaway runtime resilience** — runtime-enabled validation now avoids host
  paths that Docker may refuse to bind-mount and pre-creates workspace-scoped
  data directories before containers start.
- **Service contract correctness** — approval-gate and devops MCP services now
  use the correct package entrypoint, host-port wiring, and healthcheck
  interpreter.
- **Release/version visibility** — installs now stamp a real harness release
  version when a `VERSION` file is present instead of falling back to the branch
  name.
- **Strict regression hygiene** — SQLite-backed multi-tenant tests now close
  owned connections, keeping the full suite clean even under `pytest -W error`.

### New in 2.2

- **`VERSION`** — canonical release marker for the harness, currently set to
  `2.2`; consumed by runtime manifests and now by install metadata stamping.
- **Expanded regression assertions** in `tests/test_factory_install.py` to verify
  release-version stamping and runtime manifest version propagation during a
  throwaway install.

### Fixed in 2.2

- **Throwaway runtime target relocation** — `scripts/validate_throwaway_install.py`
  now redirects runtime-enabled throwaway targets away from system temp roots
  such as `/tmp` when Docker file sharing may reject those mounts.
- **Workspace data directory creation** — `scripts/factory_workspace.py` now
  pre-creates workspace-scoped `data/memory/<instance>` and
  `data/bus/<instance>` directories before compose startup, preventing bind-mount
  initialization failures.
- **Approval gate startup** — `factory_runtime/apps/approval_gate/main.py` now
  launches Uvicorn via the `factory_runtime.apps.approval_gate.main:app` module
  path instead of the legacy `apps.*` path.
- **DevOps MCP runtime contract** — `compose/docker-compose.mcp-devops.yml` now
  uses the correct host-port mapping for `docker-compose-mcp` vs.
  `test-runner-mcp`, and both healthchecks invoke `python3` consistently.
- **Strict warning-mode test stability** — `tests/test_multi_tenant.py` now
  closes `AgentBus` and `MemoryStore` explicitly so the full suite remains clean
  under `pytest -W error` without leaking SQLite connections.

### Changed in 2.2

- **`scripts/install_factory.py`** — install/update flows now prefer a checked-in
  `VERSION` file for the human-readable lock metadata version when no explicit
  ref is supplied.
- **`tests/test_throwaway_runtime_docker.py`** — expanded relocation coverage now
  models `/tmp` and custom `TMPDIR` scenarios explicitly.
- **`tests/test_regression.py`** and **`tests/test_factory_install.py`** — added
  regressions for approval-gate entrypoint wiring, devops MCP health/port
  contracts, and release-version propagation through installed artifacts.

### Validation for 2.2

- Re-ran the full strict regression path for this release:
  - `pytest -x -W error tests`
  - quality gate (`black` / `flake8` / `isort`)
  - `./tests/run-integration-test.sh`
  - `scripts/validate_throwaway_install.py --target /tmp/software-factory-throwaway-regression`

## [2.1] — 2026-04-08

### Summary

Release 2.1 is a hardening and production-readiness milestone built on top of the
multi-tenant foundation introduced in 2.0. The focus areas are:

- **MCP runtime reliability** — correct service startup under the `factory_runtime`
  package layout, full port-contract guarantees, and deterministic lifecycle
  transitions (start → healthy → stopped → cleaned up).
- **Production readiness** — all seven identified production-readiness findings
  resolved across Dockerfiles, healthchecks, CI, and commit-tracking.
- **Test coverage** — new Docker end-to-end regression suite, expanded install and
  multi-tenant suites, and the published MCP Runtime Mitigation Plan.
- **Registry hygiene** — stale-entry recovery, port-conflict rollback, and clean
  `*.db` tracking exclusion.

### Added

- **`tests/test_throwaway_runtime_docker.py`** — new Docker end-to-end test that
  spins up a throwaway target install against a seeded registry, verifies non-default
  port-block allocation, and probes all generated MCP localhost URLs for reachability.
- **`docs/MCP-RUNTIME-MITIGATION-PLAN.md`** — comprehensive 5-step mitigation plan
  documenting root-cause analysis and required validations for the MCP runtime
  hardening work.
- **`docs/architecture/ADR-011-Agent-Worker-Liveness-Contract.md`** — new ADR
  defining the `run-queue` liveness contract for the agent-worker container.
- **`pytest.ini`** — added `docker` marker declaration so Docker-gated tests are
  filterable without warnings.

### Fixed

- **MCP service startup** — restored correct `factory_runtime` package-qualified
  import paths in all MCP server Dockerfiles; services that previously failed to
  start due to module-not-found errors now boot cleanly.
- **Port and packaging contracts** — `factory_stack.py` now validates that every
  service inside a compose project binds on its expected internal port; divergence
  raises a clear error before containers are launched.
- **Lifecycle state truthfulness** — `factory_stack.py` now writes `running`,
  `stopped`, and `error` registry states atomically; the previous state was
  sometimes left as `starting` after a failed compose up.
- **Port recovery** — if `compose up` fails after a port-index was already reserved
  in the registry, the reservation is rolled back so a subsequent start attempt can
  claim a clean slot.
- **Foreground mode** — `factory_stack start --foreground` now blocks correctly and
  forwards compose stdout/stderr in real time; previously it returned immediately.
- **Agent-worker metadata** — the `agent-worker` container's `run-queue` entrypoint
  now records a truthful `agent_worker_mode` field in the runtime manifest.
- **All 7 production-readiness findings** resolved:
  1. All Dockerfiles pin their runtime dependencies to exact versions.
  2. All MCP service healthchecks probe the correct `/sse` endpoint.
  3. The `mock-llm-gateway` Dockerfile pins `fastapi`, `uvicorn`, and `pydantic`.
  4. The `factory_stack.py` commit-tracking path writes to the correct location.
  5. CI workflow matrix covers the install regression suite.
  6. `verify_factory_install.py` reports the correct MCP health endpoint.
  7. The `HANDOUT.md` and `CHEAT_SHEET.md` reference the current command surface.
- **Registry hygiene** — `validate_throwaway_install.py` and `verify_factory_install.py`
  no longer leave stale workspace entries when a validation run exits early.

### Changed

- **`factory_runtime/apps/mcp/agent_bus/bus.py`** — bus now rejects messages that
  exceed the per-workspace quota with a `429 Too Many Requests` instead of silently
  dropping them.
- **`factory_runtime/apps/mcp/memory/store.py`** — store enforces the
  `X-Workspace-ID` header on all write operations; previously only reads were gated.
- **`factory_runtime/apps/approval_gate/`** — approval-gate bus client retries on
  transient connection errors (up to 3 attempts with backoff) instead of failing
  immediately.
- **`scripts/factory_workspace.py`** — `build_runtime_config` resolves the preferred
  port index from the registry before falling back to auto-allocation; prevents
  unnecessary port-block churn on restarts.
- **Expanded `tests/test_factory_install.py`** — +630 lines: rollback-on-failure
  coverage, explicit port-conflict rejection, and workspace-purge lifecycle tests.
- **Expanded `tests/test_multi_tenant.py`** — +61 lines: cross-workspace data
  isolation verified at the FastMCP transport layer.

### Removed

- **`run_test.py`**, **`test_subprocess_docker.py`** — ad-hoc debug scripts removed
  from the repo root; replaced by the structured test suite.

### Chore / CI

- Fixed pre-existing `black`, `isort`, and `flake8` violations across
  `factory_runtime/` and `tests/` to restore a clean quality gate.
- Added `*.db` to `.gitignore`; replaced tracked SQLite files with `.gitkeep`
  placeholders so the data directories are preserved without committing live data.

---

## [2.0] — 2026-03-XX

Initial multi-tenant release. Introduced the shared workspace registry, per-project
port-block allocation, multi-tenant `AgentBus` and `MemoryStore` isolation, and the
VS Code window lifecycle hooks.

---

## [1.x] — Earlier

Single-tenant prototype. See git history prior to tag `single-tenant-finished`.
