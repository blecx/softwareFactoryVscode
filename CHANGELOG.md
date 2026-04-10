# Changelog

All notable changes to **Software Factory for VS Code** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased] — 2026-04-10

### Unreleased Summary

Post-`2.2` hardening work focused on making namespace-first upgrades more truthful
under real target updates, especially when an installed factory checkout already
has local edits or when a restored workspace needs a quick runtime truth check
before endpoint probing.

### Newly Added

- **Runtime preflight workflow** — `scripts/factory_stack.py preflight`, matching
  VS Code task wiring, and updated install guidance now validate service
  inventory, expected host ports, runtime manifest alignment, and generated
  workspace MCP URLs before live probes run.
- **Update regression coverage** — `tests/test_factory_install.py` now covers
  dirty installed checkouts that trigger updater-created `local-backup-*`
  branches during refresh, and verifies that release metadata is preserved.

### Newly Fixed

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
  release version (`2.2`) instead of a branch label like `main`.

### Commits

- `9b29275` — `Harden namespace-first install upgrade and runtime preflight`
- `189d46f` — `Fix dirty install updates targeting backup branches`
- `47952f7` — `Preserve release version metadata on updates`

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
