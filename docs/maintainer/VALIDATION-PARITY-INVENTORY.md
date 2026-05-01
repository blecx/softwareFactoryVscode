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

| Surface                                                                                                                                                                                                                                                                                                                                                            | Classification           | Why later phases must preserve or account for it                                                                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)                                                                                                                                                                                                                                                                                                       | Authoritative            | Defines the remote GitHub job graph, exact check names, and the aggregate production gate dependency chain.                                                                                                          |
| [`../architecture/ADR-006-Local-CI-Parity-Prechecks.md`](../architecture/ADR-006-Local-CI-Parity-Prechecks.md)                                                                                                                                                                                                                                                     | Authoritative            | Declares that `.github/workflows/ci.yml` is the minimum local precheck contract and names `./.venv/bin/python ./scripts/local_ci_parity.py` as the primary local parity path.                                        |
| [`../setup-github-repository.md`](../setup-github-repository.md)                                                                                                                                                                                                                                                                                                   | Authoritative            | Documents the exact branch-protection check names that maintainers are expected to enforce on GitHub.                                                                                                                |
| [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)                                                                                                                                                                                                                                                                                             | Derivative               | Mirrors the CI contract locally, defines the production group taxonomy, and exposes the canonical `--mode production` aggregate replay.                                                                              |
| [`../../.vscode/tasks.json`](../../.vscode/tasks.json)                                                                                                                                                                                                                                                                                                             | Derivative               | Wraps the canonical local parity command in the `✅ Validate: Local CI Parity` workspace task.                                                                                                                       |
| [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md)                                                                                                                                                                                                                                                                                                           | Derivative               | Requires local parity before PR handoff and mandates pager-free GitHub polling during merge automation.                                                                                                              |
| [`../../.copilot/skills/resolve-issue-workflow/SKILL.md`](../../.copilot/skills/resolve-issue-workflow/SKILL.md), [`../../.copilot/skills/pr-merge-workflow/SKILL.md`](../../.copilot/skills/pr-merge-workflow/SKILL.md), and [`../../.copilot/skills/approved-plan-execution-workflow/SKILL.md`](../../.copilot/skills/approved-plan-execution-workflow/SKILL.md) | Derivative               | Re-state the canonical local validation gate and the queue/merge polling rules that execute against GitHub truth.                                                                                                    |
| [`../../scripts/noninteractive_gh.py`](../../scripts/noninteractive_gh.py)                                                                                                                                                                                                                                                                                         | Derivative               | Provides the one-shot pager-free GitHub issue/PR/check polling payloads used by queue and merge automation.                                                                                                          |
| [`../../tests/test_regression.py`](../../tests/test_regression.py)                                                                                                                                                                                                                                                                                                 | Derivative               | Locks documentation, workflow, and validation-contract wording so parity drift shows up as a regression failure.                                                                                                     |
| [`../../scripts/setup-github-repo.sh`](../../scripts/setup-github-repo.sh)                                                                                                                                                                                                                                                                                         | Accidental shadow policy | Configures branch protection from a stale three-check list and writes its payload under `/tmp`, so following it today would weaken the documented protection contract and violate the repo-owned temp boundary rule. |

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
production-only diagnostic jobs, uses an explicit 45-minute job timeout that
matches the canonical production aggregate watchdog budget, and refreshes the
canonical aggregate bundle from their already-successful results via the
CI-only fast path:

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

### Bounded official waits after issue #232

Issue `#232` closes the loop on the official validation surfaces identified by
issue `#224`: the canonical local parity path, the promoted Docker/runtime
proof lane, pager-free PR-check polling, and the production-only GitHub jobs
now all carry explicit deadline-backed terminal behavior.

The concrete watchdog-backed local parity anchors are run_command() / run_step(), run_git(), and run_docker_e2e_validation() in `scripts/local_ci_parity.py`.

| Surface                                                                                                                                                                                                                                                                        | Current wait behavior                                                                                                                   | Why it is hang-prone                                                                                                                   |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `run_command()` / `run_step()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)                                                                                                                                                                       | Runs every default and fresh-checkout parity subprocess through the shared watchdog-backed timeout wrapper.                             | Stuck child processes now terminate with explicit timeout findings and replay guidance instead of waiting indefinitely.                |
| `run_git()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)                                                                                                                                                                                          | Applies the same watchdog deadline to git ref/worktree helper calls used by revision resolution and fresh-checkout state detection.     | Wedged git calls now fail explicitly, so revision discovery and fresh-checkout setup cannot hang forever.                              |
| `run_docker_e2e_validation()` in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)                                                                                                                                                                        | Executes the promoted Docker E2E runtime-proof lane with the same configured watchdog used by the rest of the parity command.           | Runtime-proof hangs now terminate with a blocking timeout report and a focused replay command instead of stalling the production lane. |
| Queue / merge polling rules in [`../../.copilot/skills/pr-merge-workflow/SKILL.md`](../../.copilot/skills/pr-merge-workflow/SKILL.md) and [`../../.copilot/skills/approved-plan-execution-workflow/SKILL.md`](../../.copilot/skills/approved-plan-execution-workflow/SKILL.md) | Use pager-free PR-check polling with `--wait --timeout-seconds 600` and stop on `pending-timeout`.                                      | Automation now reaches a deterministic blocker state instead of spinning forever on a stuck `pending` check.                           |
| GitHub Actions jobs in [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)                                                                                                                                                                                            | Encode explicit `timeout-minutes` values that match the canonical validation-policy watchdog budgets for the official CI-critical jobs. | Remote CI now fails on budget overruns with explicit job-level timeout evidence instead of inheriting unrelated runner defaults.       |

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
still supports one-shot JSON payloads with `watch_mode: false` for scriptable
single reads, but it now also exposes a bounded `--wait` mode with explicit
poll intervals, a repo-owned timeout, and `summary.overall = pending-timeout`
when GitHub readiness does not converge in time.

## How later phases should use this

- Preserve the seven check names above unless a later change deliberately
  coordinates GitHub branch protection, `.github/workflows/ci.yml`, and the
  derivative workflow/docs surfaces together.
- Treat `VALIDATION-BASELINE.md` as the timing input and this inventory as the
  contract/risk map when prioritizing convergence or watchdog work.
- Preserve the explicit watchdog/time-budget semantics on purpose rather than
  regressing to unbounded subprocess, git, polling, or CI-job waits.
- Reconcile `scripts/setup-github-repo.sh` deliberately; do not let the stale
  three-check payload continue masquerading as the current protection truth.
