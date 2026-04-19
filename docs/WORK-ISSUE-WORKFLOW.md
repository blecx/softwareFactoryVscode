# Copilot-native issue / PR / merge workflow

This repository's canonical issue workflow is **Copilot-native**.

## Canonical path

Use these Copilot agents in VS Code Chat:

1. `@create-issue`
   - draft or create a template-compliant issue
2. `@resolve-issue`
   - implement one scoped issue into one PR
3. `@pr-merge`
   - validate, merge, and close the linked issue
4. `@queue-backend` or `@queue-phase-2`
   - continue the repeatable one-issue-at-a-time loop with a manual checkpoint between iterations

## Loop rules

- One issue = one PR = one merge.
- Stop immediately on blocked PRs, CI failures, merge conflicts, or workflow errors.
- Require explicit operator approval before continuing to the next issue.
- Use `.tmp/`, never `/tmp`.

## Deterministic queue checkpoint enforcement

- Ordered queue continuation, merge, and completion prompts are guarded by `.github/hooks/github-issue-queue-guard.json`, which runs `python3 ./scripts/github_issue_queue_guard.py`.
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
- The hook blocks unsafe prompts such as “continue to the next issue”, “merge the PR”, or “close the issue” when the checkpoint is missing, incomplete, or lacks the required GitHub/cleanup evidence for the requested gate.

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
  - active issue/PR GitHub truth when available
  - PR check output when available
  - optional `factory_stack.py status` output for runtime-sensitive work
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

  Optional expanded parity:

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
- Docker image build parity exists in CI and is intentionally optional for the
  default local precheck path due host/runtime constraints; use
  `--include-docker-build` when you need full container-build parity pre-push.
- Keep the remote repository protections aligned with `docs/setup-github-repository.md` so required status checks and PR-before-merge rules backstop the local workflow.

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
