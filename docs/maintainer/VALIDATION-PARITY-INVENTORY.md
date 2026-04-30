# Validation parity inventory, required checks, and hang risks

This document is the **tracked successor location** for the phase-1 parity-surface and hang-risk inventory gathered for umbrella issue `#222` and child issue `#224`.

- **Status:** observation-only inventory
- **Authority boundary:** this report records the current contract-bearing surfaces and known wait paths; it does **not** rename checks, change branch protection, or introduce new timeout policy.
- **Baseline input:** [`VALIDATION-BASELINE.md`](VALIDATION-BASELINE.md)
- **Structured companion data:** [`../../manifests/validation-parity-inventory.json`](../../manifests/validation-parity-inventory.json)

## Scope and boundaries

This inventory exists so later convergence and watchdog issues can preserve the
right validation contract on purpose instead of accidentally deleting or
weakening required surfaces.

What this artifact does:

- records the current surfaces as **authoritative, derivative, or accidental shadow policy**;
- classifies the current parity-locked validation surfaces as authoritative,
  derivative, or accidental shadow policy;
- records the exact current required check names and the aggregate production
  authority lane; and
- identifies the known CI-critical wait or hang-prone paths that later watchdog
  work must address deliberately.

What this artifact does **not** do:

- redefine the validation contract;
- rename GitHub check names or production groups; or
- claim that the current waits already satisfy the eventual watchdog policy.

## Current parity-locked validation surfaces

| Surface | Classification | Why later phases must preserve or account for it |
| --- | --- | --- |
| [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | Authoritative | Defines the remote GitHub job graph, exact check names, and the aggregate production gate dependency chain. |
| [`../architecture/ADR-006-Local-CI-Parity-Prechecks.md`](../architecture/ADR-006-Local-CI-Parity-Prechecks.md) | Authoritative | Declares that `.github/workflows/ci.yml` is the minimum local precheck contract and names `./.venv/bin/python ./scripts/local_ci_parity.py` as the primary local parity path. |
| [`../setup-github-repository.md`](../setup-github-repository.md) | Authoritative | Documents the exact branch-protection check names that maintainers are expected to enforce on GitHub. |
| [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) | Derivative | Mirrors the CI contract locally, defines the production group taxonomy, and exposes the canonical `--mode production` aggregate replay. |
| [`../../.vscode/tasks.json`](../../.vscode/tasks.json) | Derivative | Wraps the canonical local parity command in the `✅ Validate: Local CI Parity` workspace task. |
| [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md) | Derivative | Requires local parity before PR handoff and mandates pager-free GitHub polling during merge automation. |
| [`../../.copilot/skills/resolve-issue-workflow/SKILL.md`](../../.copilot/skills/resolve-issue-workflow/SKILL.md), [`../../.copilot/skills/pr-merge-workflow/SKILL.md`](../../.copilot/skills/pr-merge-workflow/SKILL.md), and [`../../.copilot/skills/approved-plan-execution-workflow/SKILL.md`](../../.copilot/skills/approved-plan-execution-workflow/SKILL.md) | Derivative | Re-state the canonical local validation gate and the queue/merge polling rules that execute against GitHub truth. |
| [`../../scripts/noninteractive_gh.py`](../../scripts/noninteractive_gh.py) | Derivative | Provides the one-shot pager-free GitHub issue/PR/check polling payloads used by queue and merge automation. |
| [`../../tests/test_regression.py`](../../tests/test_regression.py) | Derivative | Locks documentation, workflow, and validation-contract wording so parity drift shows up as a regression failure. |
| [`../../scripts/setup-github-repo.sh`](../../scripts/setup-github-repo.sh) | Accidental shadow policy | Configures branch protection from a stale three-check list and writes its payload under `/tmp`, so following it today would weaken the documented protection contract and violate the repo-owned temp boundary rule. |

## Exact current required checks and aggregate production authority

The current GitHub-required check names are:

1. `Python Code Quality (Lint & Format)`
2. `Architectural Boundary Tests`
3. `PR Template Conformance`
4. `Production Docs Contract`
5. `Production Docker Build Parity`
6. `Production Runtime Proofs`
7. `Internal Production Gate — Docker Parity & Recovery Proofs`

The first six names come directly from the job names in
[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) and are repeated in
[`../setup-github-repository.md`](../setup-github-repository.md) for branch
protection setup.

The final check, `Internal Production Gate — Docker Parity & Recovery Proofs`,
is the **aggregate production authority lane**. It depends on the three
production-only diagnostic jobs and now refreshes the canonical aggregate
bundle from their already-successful results via the CI-only fast path:

```text
python3 ./scripts/local_ci_parity.py --mode production --production-group aggregate --production-groups-only --ci-production-readiness-bundle-only
```

Within `scripts/local_ci_parity.py`, the production-group taxonomy is currently:

- `docs-contract`
- `docker-builds`
- `runtime-proofs`
- aggregate default = all three groups above

Later migration work must preserve those names intentionally unless it also
coordinates the matching branch-protection and workflow-surface changes.

## Current accidental shadow-policy finding

[`../../scripts/setup-github-repo.sh`](../../scripts/setup-github-repo.sh) is
currently an **accidental shadow policy** rather than a safe source of truth.

It diverges from the documented/current contract in two ways:

1. its `required_status_checks.contexts` payload contains only:
   - `Python Code Quality (Lint & Format)`
   - `Architectural Boundary Tests`
   - `PR Template Conformance`
2. it writes the temporary branch-protection payload to
   `` `/tmp/branch-protection-payload.json` ``, even though the canonical issue
   workflow requires repo-owned temporary state under `.tmp/`.

That means later convergence work must treat the setup script as a drift surface
that needs deliberate reconciliation, not as the authoritative definition of the
current required-check set.

## CI-critical wait and hang inventory

### Unbounded or externally bounded today

The highest-risk current local wait surface is `run_command() / run_step()` in
`scripts/local_ci_parity.py`, because it fans out across most of the default
and fresh-checkout parity lanes without an explicit timeout.

| Surface | Current wait behavior | Why it is hang-prone |
| --- | --- | --- |
| `run_command()` / `run_step()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) | Calls `subprocess.run(...)` with no timeout wrapper for the default local parity steps and the fresh-checkout replay path. | Any stuck child process (`./setup.sh`, `pytest`, integration regression, Docker build helpers, or the child parity replay) can wait indefinitely. |
| `run_git()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) | Calls `subprocess.run(...)` with no timeout while resolving refs, merge-bases, or worktree state. | A wedged git call in the fresh-checkout or parity path can block the entire validation flow with no watchdog. |
| `run_docker_e2e_validation()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) | Launches the promoted Docker E2E runtime-proof pytest lane via a direct `subprocess.run(...)` with no timeout. | Docker/runtime proof hangs remain unbounded on `origin/main`, even though the lane is part of the production critical path. |
| Queue / merge polling rules in [`../../.copilot/skills/pr-merge-workflow/SKILL.md`](../../.copilot/skills/pr-merge-workflow/SKILL.md) and [`../../.copilot/skills/approved-plan-execution-workflow/SKILL.md`](../../.copilot/skills/approved-plan-execution-workflow/SKILL.md) | Require non-interactive polling until GitHub checks reach a terminal state. | The workflow contract does not yet encode a max-attempt or elapsed-time bound, so automation needs an external watchdog to avoid waiting forever on a stuck `pending` check. |

### Bounded waits already present

Not every wait is unbounded. The current production runtime-proof tests already
contain some bounded waits that later watchdog work should distinguish from the
unbounded subprocess/polling surfaces above:

- [`../../tests/test_throwaway_runtime_docker.py`](../../tests/test_throwaway_runtime_docker.py)
  uses `_wait_until_reachable(url, max_wait_seconds=30)` with a 1-second retry
  loop for service reachability.
- The same file uses attempt-limited runtime verification retries with a
  configurable delay between attempts.
- The helper functions in that file also use explicit network timeouts such as
  `urlopen(..., timeout=4.0)` and `httpx.Client(timeout=10.0)`.

Those waits are still CI-critical, but they are already bounded and therefore
belong in a different remediation bucket than the unbounded parity-script and
queue-polling paths.

## Current GitHub polling boundary

[`../../scripts/noninteractive_gh.py`](../../scripts/noninteractive_gh.py)
intentionally returns one-shot JSON payloads with `watch_mode: false`. That is
useful because it keeps polling pager-free and scriptable, but it also means the
helper itself does **not** provide a built-in polling deadline or watch loop.
Later watchdog work therefore has to add explicit bounds in the caller/wrapper
layer instead of assuming the helper already solves the wait problem.

## How later phases should use this

- Preserve the seven check names above unless a later change deliberately
  coordinates GitHub branch protection, `.github/workflows/ci.yml`, and the
  derivative workflow/docs surfaces together.
- Treat `VALIDATION-BASELINE.md` as the timing input and this inventory as the
  contract/risk map when prioritizing convergence or watchdog work.
- Replace the unbounded subprocess and polling paths with explicit watchdog
  behavior on purpose rather than by ad-hoc script edits.
- Reconcile `scripts/setup-github-repo.sh` deliberately; do not let the stale
  three-check payload continue masquerading as the current protection truth.
