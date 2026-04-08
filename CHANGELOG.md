# Changelog

All notable changes to **Software Factory for VS Code** are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [2.1] — 2026-04-08

### Summary

Release 2.1 is a hardening and production-readiness milestone built on top of the
multi-tenant foundation introduced in 2.0.  The focus areas are:

* **MCP runtime reliability** — correct service startup under the `factory_runtime`
  package layout, full port-contract guarantees, and deterministic lifecycle
  transitions (start → healthy → stopped → cleaned up).
* **Production readiness** — all seven identified production-readiness findings
  resolved across Dockerfiles, healthchecks, CI, and commit-tracking.
* **Test coverage** — new Docker end-to-end regression suite, expanded install and
  multi-tenant suites, and the published MCP Runtime Mitigation Plan.
* **Registry hygiene** — stale-entry recovery, port-conflict rollback, and clean
  `*.db` tracking exclusion.

### Added

* **`tests/test_throwaway_runtime_docker.py`** — new Docker end-to-end test that
  spins up a throwaway target install against a seeded registry, verifies non-default
  port-block allocation, and probes all generated MCP localhost URLs for reachability.
* **`docs/MCP-RUNTIME-MITIGATION-PLAN.md`** — comprehensive 5-step mitigation plan
  documenting root-cause analysis and required validations for the MCP runtime
  hardening work.
* **`docs/architecture/ADR-011-Agent-Worker-Liveness-Contract.md`** — new ADR
  defining the `run-queue` liveness contract for the agent-worker container.
* **`pytest.ini`** — added `docker` marker declaration so Docker-gated tests are
  filterable without warnings.

### Fixed

* **MCP service startup** — restored correct `factory_runtime` package-qualified
  import paths in all MCP server Dockerfiles; services that previously failed to
  start due to module-not-found errors now boot cleanly.
* **Port and packaging contracts** — `factory_stack.py` now validates that every
  service inside a compose project binds on its expected internal port; divergence
  raises a clear error before containers are launched.
* **Lifecycle state truthfulness** — `factory_stack.py` now writes `running`,
  `stopped`, and `error` registry states atomically; the previous state was
  sometimes left as `starting` after a failed compose up.
* **Port recovery** — if `compose up` fails after a port-index was already reserved
  in the registry, the reservation is rolled back so a subsequent start attempt can
  claim a clean slot.
* **Foreground mode** — `factory_stack start --foreground` now blocks correctly and
  forwards compose stdout/stderr in real time; previously it returned immediately.
* **Agent-worker metadata** — the `agent-worker` container's `run-queue` entrypoint
  now records a truthful `agent_worker_mode` field in the runtime manifest.
* **All 7 production-readiness findings** resolved:
  1. All Dockerfiles pin their runtime dependencies to exact versions.
  2. All MCP service healthchecks probe the correct `/sse` endpoint.
  3. The `mock-llm-gateway` Dockerfile pins `fastapi`, `uvicorn`, and `pydantic`.
  4. The `factory_stack.py` commit-tracking path writes to the correct location.
  5. CI workflow matrix covers the install regression suite.
  6. `verify_factory_install.py` reports the correct MCP health endpoint.
  7. The `HANDOUT.md` and `CHEAT_SHEET.md` reference the current command surface.
* **Registry hygiene** — `validate_throwaway_install.py` and `verify_factory_install.py`
  no longer leave stale workspace entries when a validation run exits early.

### Changed

* **`factory_runtime/apps/mcp/agent_bus/bus.py`** — bus now rejects messages that
  exceed the per-workspace quota with a `429 Too Many Requests` instead of silently
  dropping them.
* **`factory_runtime/apps/mcp/memory/store.py`** — store enforces the
  `X-Workspace-ID` header on all write operations; previously only reads were gated.
* **`factory_runtime/apps/approval_gate/`** — approval-gate bus client retries on
  transient connection errors (up to 3 attempts with backoff) instead of failing
  immediately.
* **`scripts/factory_workspace.py`** — `build_runtime_config` resolves the preferred
  port index from the registry before falling back to auto-allocation; prevents
  unnecessary port-block churn on restarts.
* **Expanded `tests/test_factory_install.py`** — +630 lines: rollback-on-failure
  coverage, explicit port-conflict rejection, and workspace-purge lifecycle tests.
* **Expanded `tests/test_multi_tenant.py`** — +61 lines: cross-workspace data
  isolation verified at the FastMCP transport layer.

### Removed

* **`run_test.py`**, **`test_subprocess_docker.py`** — ad-hoc debug scripts removed
  from the repo root; replaced by the structured test suite.

### Chore / CI

* Fixed pre-existing `black`, `isort`, and `flake8` violations across
  `factory_runtime/` and `tests/` to restore a clean quality gate.
* Added `*.db` to `.gitignore`; replaced tracked SQLite files with `.gitkeep`
  placeholders so the data directories are preserved without committing live data.

---

## [2.0] — 2026-03-XX

Initial multi-tenant release.  Introduced the shared workspace registry, per-project
port-block allocation, multi-tenant `AgentBus` and `MemoryStore` isolation, and the
VS Code window lifecycle hooks.

---

## [1.x] — Earlier

Single-tenant prototype.  See git history prior to tag `single-tenant-finished`.
