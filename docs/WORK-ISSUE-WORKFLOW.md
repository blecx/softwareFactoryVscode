# Copilot-native issue / PR / merge workflow

This repository's canonical issue workflow is **Copilot-native**.

## Canonical path

Use these Copilot agents in VS Code Chat:

1. `@create-issue` — draft or create a template-compliant issue.
1. `@resolve-issue` — implement one scoped issue into one PR.
1. `@pr-merge` — validate, merge, and close the linked issue.
1. `@queue-backend` or `@queue-phase-2` — continue the repeatable
   one-issue-at-a-time loop with a manual checkpoint between iterations,
   using the same `@resolve-issue` → `@pr-merge` slice path.
1. `@execute-approved-plan` — execute a bounded approved GitHub-backed issue
   plan end-to-end when the operator explicitly says things like
   `execute the plan`, `continue the plan`, or `run the approved queue`, by
   repeating the same `@resolve-issue` → `@pr-merge` slice path automatically
   within the approved set.

## Loop rules

- One issue = one PR = one merge.
- Stop immediately on blocked PRs, CI failures, merge conflicts, or workflow errors.
- Default queue agents (`@queue-backend`, `@queue-phase-2`) require explicit
  operator approval before continuing to the next issue.
- `@execute-approved-plan` is the bounded exception: when the operator has
  explicitly approved a finite GitHub-backed issue set, it may continue
  automatically within that set until completion or a true blocker.
- Use `.tmp/`, never `/tmp`.

## Single source of truth for issue execution

The repository supports exactly one canonical issue-to-merge process:

1. `@resolve-issue` owns implementation, branch selection, local validation,
   PR-body preparation, and PR creation for one issue.
2. `@pr-merge` owns PR readiness checks, CI polling, merge, issue close, and
   post-merge cleanup.
3. `@execute-approved-plan` is the bounded multi-issue wrapper that repeats the
   same `@resolve-issue` → `@pr-merge` slice path for an explicit approved set.
4. `@queue-backend` and `@queue-phase-2` are scoped/manual-checkpoint wrappers
   over that same canonical slice path; they do **not** define a different
   implementation, PR, or merge process.

If a PR has CI errors or merge-readiness problems, return to `@resolve-issue`
to fix the root cause on the active slice, rerun the local prechecks, and then
re-enter `@pr-merge`. Do not invent a separate “fix the PR” workflow.

## Execution surfaces

Workflow execution surface is part of the supported contract.

- **Source checkout** — the `softwareFactoryVscode` repository itself. Use this surface for factory implementation work, repo tests, docs, prompts, and lifecycle helpers that already know how to resolve the companion install.
- **Generated workspace** — the host repository's `software-factory.code-workspace` file. This is the supported operator surface for tasks that need `Host Project (Root)` and the installed host contract.
- **Companion runtime metadata** — the installed host repository state under `<host>/.copilot/softwareFactoryVscode/`, including `.factory.env`, `lock.json`, and `.tmp/runtime-manifest.json`.

Routing rule:

- If a task depends on `Host Project (Root)` or validates the installed host contract, it belongs to the generated workspace or an explicit companion runtime target, not the source checkout alone.
- Repo-owned task wrappers must reject wrong-surface invocation with actionable guidance or require an explicit target; they must not silently fabricate a second runtime contract inside the source checkout.
- The canonical guard for these task surfaces is `scripts/workspace_surface_guard.py`, which fails fast when the task is launched from the source checkout without a valid generated-workspace host target.

## Non-interactive GitHub / terminal patterns

- Prefer pager-free JSON polling for GitHub state queries in automation-heavy loops. The canonical helper is `./scripts/noninteractive_gh.py`, for example:

  ```text
  ./.venv/bin/python ./scripts/noninteractive_gh.py pr-view 68
  ./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks 68
  ./.venv/bin/python ./scripts/noninteractive_gh.py issue-list --state open --limit 50 --search "routing"
  ```

- Prefer polling the helper's JSON output over `gh pr checks --watch`, pager UI, or web/watch flows when you are inside an automation loop.
- For bounded waiting, prefer `./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks <PR_NUMBER> --wait --timeout-seconds 600` over `gh pr checks --watch`, `gh run watch`, or other watch-style flows.
- If the helper returns `summary.overall = pending-timeout`, treat that as a real blocker for the current automation pass: refresh `.tmp/github-issue-queue-state.md`, report CI as still pending, and stop so the operator or a later resume can re-anchor cleanly instead of waiting indefinitely.
- If the helper does not cover a one-off query yet, use an equivalent pager-free pattern such as `GH_PAGER=cat PAGER=cat gh ... --json ...`; do not rely on the CLI deciding whether to open a pager.
- When transforming JSON in shell automation, pipe into `python3 -c '...'`, `./.venv/bin/python -c '...'`, or a dedicated script. Do **not** combine a pipe with a heredoc-based Python command such as `... | python3 - <<'PY'`, because the heredoc replaces stdin and the piped JSON never reaches `sys.stdin`.
- Long-running Docker/test output is not itself evidence of an input prompt. Before sending terminal input, confirm that the terminal explicitly requests it (for example `Enter ...`, `[y/N]`, `Username:`, or a tool-level input-needed signal).

## Deterministic queue checkpoint contract

- The queue checkpoint file `.tmp/github-issue-queue-state.md` is the shared
  state contract for `@resolve-issue`, `@pr-merge`, `@execute-approved-plan`,
  and interruption recovery.
- This repository intentionally does **not** use a global `UserPromptSubmit`
  hook for issue/PR/merge enforcement. Prompt-time hooks created a second
  workflow path and are outside the supported contract.
- Keep `.tmp/github-issue-queue-state.md` updated throughout the current issue. The minimum checkpoint fields are:
  - `active_issue`
  - `active_branch`
  - `active_pr`
  - `status`
  - `last_validation`
  - `next_gate`
  - `blocker`
- Before invoking `@pr-merge`, narrating merge readiness, or claiming that an issue is complete, extend the checkpoint with GitHub-truth evidence:
  - `issue_state`
  - `pr_state`
  - `ci_state`
  - `cleanup_state`
  - `last_github_truth`
- Canonical workflows must refuse unsafe continuation, merge, or completion
  steps when the checkpoint is missing, incomplete, or lacks the required
  GitHub/cleanup evidence, and they must explain exactly what is missing.

## Resume after interruption

- After a timeout, restart, compaction event, or tool uncertainty, re-anchor before resuming the current issue.
- Use the dedicated workflow prompt at `.github/prompts/resume-after-interruption.prompt.md` or the companion skill at `.copilot/skills/interruption-recovery-workflow/SKILL.md`.
- Capture a repo-owned recovery artifact under `.tmp/` with:

  ```text
  ./.venv/bin/python ./scripts/capture_recovery_snapshot.py
  ```

- When the interrupted task touched runtime, Docker, MCP, or workspace lifecycle state, include service diagnostics with:

  ```text
  ./.venv/bin/python ./scripts/capture_recovery_snapshot.py --include-runtime-status
  ```

- The helper writes `.tmp/interruption-recovery-snapshot.md` and records:
  - current branch
  - working tree state
  - queue checkpoint contents from `.tmp/github-issue-queue-state.md`
  - execution-surface assessment for the current editor/file/cwd when supplied
  - active issue/PR GitHub truth when available
  - PR check output when available
  - optional `factory_stack.py status` output for runtime-sensitive work
- Window reload, window close/reopen, or foreground task exit is not itself
  runtime truth. Use `factory_stack.py status` or
  `capture_recovery_snapshot.py --include-runtime-status` before assuming the
  runtime stopped or needs a fresh `start`.
- Treat the current editor/file path as advisory only. If it points under `.tmp/queue-worktrees/*` but the top-level directory is missing repo/worktree markers such as `.git`, `docs/`, or `scripts/`, classify it as a stray partial snapshot and resume from the repository root plus `.tmp/github-issue-queue-state.md` instead of treating that path as the active worktree.
- Review the recovery snapshot and update `.tmp/github-issue-queue-state.md` before resuming implementation, merge, cleanup, or queue selection.

## Required guardrails

- Issues must follow `.github/ISSUE_TEMPLATE/feature_request.yml` or `.github/ISSUE_TEMPLATE/bug_report.yml`.
- PR descriptions must follow `.github/pull_request_template.md` exactly.
- Before opening or finalizing a PR, run the local equivalents of `.github/workflows/ci.yml`:

  Primary one-command path:

  ```text
  ./.venv/bin/python ./scripts/local_ci_parity.py
  ```

  This executes release-doc policy, release-manifest parity, Black/isort/Flake8,
  `pytest tests/`, integration regression, and PR-template validation against
  `.github/pull_request_template.md`.

  Canonical production-grade parity:

  ```text
  ./.venv/bin/python ./scripts/local_ci_parity.py --mode production
  ```

  Optional build-only expansion alias:

  ```text
  ./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build
  ```

  Equivalent explicit checks (for troubleshooting/granular reruns):

  ```text
   ./.venv/bin/python ./scripts/verify_release_docs.py --repo-root . --base-rev <base> --head-rev HEAD
   ./.venv/bin/python ./scripts/factory_release.py write-manifest --repo-root . --repo-url https://github.com/blecx/softwareFactoryVscode.git --check
  ./.venv/bin/black --check factory_runtime/ scripts/ tests/
  ./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/
  ./.venv/bin/flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841
  ./.venv/bin/pytest tests/
  ./tests/run-integration-test.sh
   ./scripts/validate-pr-template.sh ./.github/pull_request_template.md
  ```

- Validate generated PR bodies locally with `./scripts/validate-pr-template.sh <pr-body-file>`
  (or `./.venv/bin/python ./scripts/local_ci_parity.py --pr-body-file <pr-body-file>`)
  before asking GitHub to enforce the same template in CI.
- The canonical blocking production-grade parity command is
  `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`; it now
  includes Docker image builds plus the promoted Docker E2E runtime proof lane.
- When you need the closest local replay of GitHub's checkout/bootstrap surface
  before merge, run
  `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout`.
- Docker image build parity remains intentionally optional for the default
  local precheck path due host/runtime constraints.
- `--include-docker-build` remains the build-only compatibility alias when you
  want container-build expansion without the full promoted production gate.
- Keep the remote repository protections aligned with `docs/setup-github-repository.md` so required status checks and PR-before-merge rules backstop the local workflow.

## Readiness closeout evidence discipline

When an issue is a readiness closeout or documentation/evidence-alignment
slice, the closing note must make the evidence bundle reproducible and bounded:

- run the focused tests for the surfaces changed by the issue;
- run `./.venv/bin/python ./scripts/local_ci_parity.py` before calling the
  slice complete;
- add targeted Docker-backed validation when the claim depends on real
  container, image, shared-mode, or cleanup truth; and
- name the deferred items that remain out of scope after the slice instead of
  implying that the whole readiness program is now universally complete.

For the current MCP harness readiness baseline, the minimum reproducible
evidence bundle is:

```text
./.venv/bin/pytest tests/test_regression.py -v
./.venv/bin/python ./scripts/local_ci_parity.py
```

The promoted strict-tenant plus stop/cleanup subset is already part of
`./.venv/bin/python ./scripts/local_ci_parity.py --mode production`. Add the
targeted `RUN_DOCKER_E2E=1` lifecycle proofs from `tests/README.md` whenever
the slice depends on other real container/image state, such as explicit
multi-workspace activation truth.

These are not optional style notes; they are the historical guardrails defined by `docs/architecture/ADR-001-AI-Workflow-Guardrails.md`, reinforced by `docs/architecture/ADR-005-Strong-Templating-Enforcement.md` and `docs/architecture/ADR-006-Local-CI-Parity-Prechecks.md`, plus `.copilot/skills/a2a-communication/SKILL.md`, `.github/workflows/ci.yml`, and the remote protection guidance in `docs/setup-github-repository.md`.

## Legacy path status

The following legacy scripts are **not** the canonical workflow and should not be used for normal issue execution:

- `scripts/work-issue.py`
- `scripts/issue-pr-merge-cleanup-loop.sh`

They exist only as historical/autonomous artifacts. The supported workflow entrypoints are the Copilot agents and `.copilot/skills/*` modules.

## Why

The Copilot-native flow keeps issue creation, implementation, merge policy, and loop orchestration aligned with the repository's current `.github/agents/*` and `.copilot/skills/*` sources of truth.

## Recommended operator sequence

For a new item:

1. Open Copilot Chat in the workspace.
2. Use `@create-issue` to create the issue from the repository template.
3. Use `@resolve-issue` with the created issue number.
4. When the PR is ready, use `@pr-merge`.
5. For ongoing queue work, switch to `@queue-backend` or `@queue-phase-2`.
6. When the operator has already approved a finite GitHub-backed issue set and
   wants continuous execution, use `@execute-approved-plan`.
