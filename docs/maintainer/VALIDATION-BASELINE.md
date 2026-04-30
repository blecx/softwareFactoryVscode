# Validation runtime baseline and hotspot evidence

This document is the **tracked successor location** for the raw phase-1 timing captures gathered for umbrella issue `#222` and child issue `#223`.

- **Status:** observation-only evidence
- **Authority boundary:** this report records current behavior; it does **not** change the validation contract, required check names, or workflow semantics.
- **Structured companion data:** [`../../manifests/validation-baseline.json`](../../manifests/validation-baseline.json)
- **Raw supporting captures:** `.tmp/validation-baseline/` and `.tmp/issue-223-gh-run-25118595701-jobs-api.json`

## Scope and boundaries

This baseline exists so later convergence / watchdog work can compare against the repository's current validation cost without guessing.

What this artifact does:

- records current local and GitHub validation timings;
- identifies the main observed hotspots and repeated setup costs; and
- points later phases at reproducible commands and captured GitHub run evidence.

What this artifact does **not** do:

- rename or redefine required checks;
- introduce a new validation taxonomy; or
- claim that the current timings are acceptable policy targets.

## Evidence sources

### Local source-of-truth captures

- `./.venv/bin/python ./scripts/local_ci_parity.py`
- `./.venv/bin/python -m pytest tests/ --durations=10 -q`

These commands were replayed on `2026-04-30` from the clean queue worktree at
`.tmp/queue-worktrees/issue-223`, which was explicitly reset to `origin/main`
so the phase-1 baseline would not accidentally include unrelated unpublished
local work from the source checkout.

### GitHub source-of-truth captures

- Workflow run: [`25118595701`](https://github.com/blecx/softwareFactoryVscode/actions/runs/25118595701)
- Raw jobs capture: `.tmp/issue-223-gh-run-25118595701-jobs-api.json`

That run exposes the same seven-check layout currently defined by
`.github/workflows/ci.yml`, so it is suitable as the remote timing baseline for
this observation-first slice.

## Current local baseline

### Canonical default local precheck

| Surface | Command | Result | Elapsed |
| --- | --- | --- | ---: |
| Default local parity baseline | `./.venv/bin/python ./scripts/local_ci_parity.py` | Pass with 1 warning (`Docker image build parity` intentionally skipped in standard mode) | 39.58 s |
| Diagnostic hotspot replay | `./.venv/bin/python -m pytest tests/ --durations=10 -q` | `374 passed, 5 skipped` | 29.56 s |

### Local hotspot interpretation

- The monolithic `pytest tests/` step consumes **29.56 s / 39.58 s = 74.68%** of
  the default local precheck wall clock.
- The current `origin/main` baseline still exposes `pytest tests/` as one broad
  parity step. It does **not** yet offer first-class named standard groups or
  named pytest bundle replays, so deeper hotspot inspection currently requires a
  separate diagnostic command such as `pytest --durations=10`.
- The default local precheck remains fast enough for routine use, but it hides
  which subsets dominate the `pytest` lane unless maintainers gather extra
  evidence explicitly.

### Slowest observed local tests/files

The `pytest --durations=10` replay reported these dominant tests on the current
baseline:

| Rank | Test | Duration |
| --- | --- | ---: |
| 1 | `tests/test_factory_install.py::test_release_update_smoke_flow` | 1.78 s |
| 2 | `tests/test_factory_install.py::test_factory_update_check_uses_live_local_source_head_when_manifest_lags` | 1.76 s |
| 3 | `tests/test_factory_install.py::test_factory_update_apply_refreshes_install_from_source_manifest` | 1.73 s |
| 4 | `tests/test_factory_install.py::test_update_ignores_local_backup_branch_and_resets_to_latest_source` | 1.68 s |
| 5 | `tests/test_factory_install.py::test_update_removes_legacy_factory_gitignore_block` | 1.61 s |
| 6 | `tests/test_factory_install.py::test_update_preserves_custom_workspace_and_env` | 1.56 s |
| 7 | `tests/test_multi_tenant.py::test_shared_service_extractors_allow_compatibility_fallback` | 1.21 s |
| 8 | `tests/test_factory_install.py::test_throwaway_target_install_regression_via_cli` | 1.07 s |
| 9 | `tests/test_legacy_cleanup.py::test_install_factory_removes_legacy_root_contract_even_if_miscreated_as_directories` | 0.93 s |
| 10 | `tests/test_factory_install.py::test_update_refresh_preserves_active_workspace_and_runtime_state` | 0.93 s |

The dominant local hotspot is therefore not formatting/linting; it is the
install/update-heavy portion of the monolithic pytest lane.

## Current GitHub CI baseline

### Overall wall clock

- Earliest job start: `2026-04-29T15:40:04Z`
- Final job completion: `2026-04-29T15:59:46Z`
- Observed GitHub wall-clock runtime: **1182 s (19 m 42 s)**

That makes the current GitHub wall clock roughly **29.86×** slower than the
default local precheck (`1182 / 39.58`).

### Job-by-job timing breakdown

| Check / job | Elapsed | `Install dependencies` | Dominant in-job work |
| --- | ---: | ---: | --- |
| `PR Template Conformance` | 3 s | n/a | checkout/validation only |
| `Python Code Quality (Lint & Format)` | 222 s | 189 s | `Run unit tests` = 15 s |
| `Architectural Boundary Tests` | 3 s | n/a | isolated integration test |
| `Production Docs Contract` | 185 s | 182 s | diagnostic step effectively 0 s |
| `Production Docker Build Parity` | 323 s | 180 s | docker-build diagnostics = 139 s |
| `Production Runtime Proofs` | 513 s | 190 s | runtime-proof diagnostics = 319 s |
| `Internal Production Gate — Docker Parity & Recovery Proofs` | 653 s | 186 s | canonical aggregate gate = 462 s |

### Remote hotspot interpretation

- The single longest job is the **aggregate production gate** at **653 s**.
- The largest pre-aggregate diagnostic job is **Production Runtime Proofs** at
  **513 s**.
- The repository currently pays **repeated dependency/bootstrap cost** across
  five Python-backed jobs. Summed across those jobs, `Install dependencies`
  consumes **927 s** of cumulative runner time.
- The `Python Code Quality (Lint & Format)` job spends **189 s** on dependency
  installation and only **15 s** on the `Run unit tests` step, which means the
  GitHub bottleneck is dominated by repeated setup and production-grade replay,
  not by lint/test execution alone.
- The critical path is currently: parallel diagnostic stage → `Production Runtime
  Proofs` completes last → canonical aggregate production gate reruns the
  production lane.

## Main findings for later phases

1. **Local hotspot:** the current default local parity command is dominated by
   the single monolithic `pytest tests/` lane.
2. **Remote hotspot:** the current GitHub critical path is dominated by the
   promoted production runtime proofs plus the later canonical aggregate
   production gate.
3. **Repeated bootstrap/setup cost is material:** `Install dependencies`
   accounts for `927 s` of cumulative runner time across the Python-backed jobs.
4. **Current local parity lacks first-class bundle replay on `origin/main`:**
   maintainers need separate diagnostic commands (for example
   `pytest --durations=10`) to isolate local hotspots.
5. **Observation only:** these findings justify later convergence / watchdog work,
   but they do not by themselves authorize renaming checks, changing branch
   protection, or altering the canonical parity meaning.

## Reproducibility commands

Use these commands when refreshing this baseline intentionally:

```text
./.venv/bin/python ./scripts/local_ci_parity.py
./.venv/bin/python -m pytest tests/ --durations=10 -q
GH_PAGER=cat gh run view 25118595701 --repo blecx/softwareFactoryVscode --json jobs,url
```

If later phases need a refreshed remote baseline from a newer branch or run,
they should preserve the same observation-only discipline and update the tracked
JSON companion instead of silently replacing current evidence with undocumented
measurements.

## How later phases should use this

- Issue `#224` should treat this report as the runtime baseline input when it
  inventories parity-locked surfaces, required check names, and hang risks.
- Later convergence and watchdog issues should compare against these numbers
  explicitly instead of claiming improvement without a baseline.
- Any future optimization or timeout policy must cite the measured hotspots here
  before redefining validation flow.
