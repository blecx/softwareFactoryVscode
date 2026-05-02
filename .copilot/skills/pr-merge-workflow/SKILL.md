<skill>
<name>pr-merge-workflow</name>
<description>Workflow or rule module for reviewing, validating, and merging GitHub PRs.</description>
<file>
# PR Merge Workflow (Module)

## Objective

Provides context and instructions for the `pr-merge-workflow` skill module.

This is the canonical PR-validation, merge, and closeout half of the
repository's issue → PR → merge process.

## When to Use

- A PR is ready or nearly ready and needs merge validation.
- An issue number needs to be resolved through PR discovery and merge.
- A PR has CI or merge-readiness issues that need triage before deciding
  whether to merge or hand back to implementation.

## When Not to Use

- Do not use this when the current task does not involve concluding, reviewing, or merging PRs.

## Instructions

1. Verify PR is open, mergeable, and not draft using pager-free JSON queries:
   `./.venv/bin/python ./scripts/noninteractive_gh.py pr-view <PR_NUMBER>`
   - Prefer this helper (or another pager-free `gh ... --json ...` pattern) over watch/web flows while you are inside an automation loop.
   - Refresh this GitHub truth immediately before any readiness, merge, queue-advance, or blocker narration; do not rely on earlier helper output, stale checkpoint state, memory, or terminal silence.
   - Treat PR head branch provenance as a hard gate: the `headRefName` reported by GitHub must match the current local branch and `.tmp/github-issue-queue-state.md` `active_branch` before you claim readiness or continue toward merge.
2. Confirm the PR description follows `.github/pull_request_template.md` and validate the body locally with:
   `./scripts/validate-pr-template.sh .tmp/pr-body-<issue-number>.md`
3. Confirm local CI-equivalent prechecks from `.github/workflows/ci.yml` were run for the PR branch and that evidence is present in the PR body:
   - `./.venv/bin/black --check factory_runtime/ scripts/ tests/`
   - `./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/`
   - `./.venv/bin/flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841`
   - `./.venv/bin/pytest tests/`
   - `./tests/run-integration-test.sh`
4. Confirm required CI/CD checks are green by explicitly polling:
   `./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks <PR_NUMBER>`
   - For bounded waiting in automation, prefer `./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks <PR_NUMBER> --wait --timeout-seconds 600`.
   - Prefer JSON polling over `gh pr checks --watch`, `gh run watch`, or other watch/pager UI flows; they add unnecessary terminal churn in repo automation.
   - Treat PR readiness as GitHub truth only. Do **not** infer status from local PID files, process liveness, terminal silence, or similar host-side heuristics; use `statusCheckRollup`, mergeability, and related GitHub JSON metadata instead.
   - Refresh `.tmp/github-issue-queue-state.md` from GitHub truth before merge/close narration. Record `issue_state`, `pr_state`, `ci_state`, `cleanup_state`, and `last_github_truth`; that checkpoint is the shared state contract used by canonical workflows and interruption recovery.
   - `last_github_truth` must preserve the exact `pr-view` / `pr-checks` helper command(s), selector(s), and result summary used for the current claim; vague prose or stale summaries are not sufficient provenance.
   - If `headRefName`, the local branch, and checkpoint `active_branch` disagree, stop and hand the slice back for re-anchor/root-cause repair instead of narrating merge readiness.
   - If the helper reports `summary.overall = pending-timeout`, stop the automatic wait, record the still-pending CI state in `.tmp/github-issue-queue-state.md`, and return a blocker/resume point instead of continuing to poll indefinitely.
   - If checks fail or the PR is not mergeable, do not invent a separate repair path. Hand the slice back to `resolve-issue`, quote the exact failing command/check, relevant error text, and suspected root cause from the fresh evidence, rerun local prechecks there, and then re-enter `pr-merge`.
   - Do **not** permit a second repair change without refreshed evidence from the new failure state; trial-and-error churn is non-compliant.
5. Merge with squash and delete branch:
   `gh pr merge <PR_NUMBER> --squash --delete-branch`
6. Comment and close linked issue (if needed).
7. Clean transient `.tmp` files MANDATORILY using:
   `rm -f .tmp/pr-body-<issue-number>.md .tmp/issue-<issue-number>-*.md`
8. Sync local `main` via `git checkout main && git pull` and verify final state.

## Required Checks

- Choose the correct repo and validation gate before merge.
- Require real validation evidence in the PR body.
- For UI/UX-affecting changes, require recorded UX authority resolution.
- Capture merge metrics when tooling supports it.
- Ensure the repository protections described in `docs/setup-github-repository.md` are compatible with the intended merge path (required status checks, PR-before-merge, branch cleanup).

## Guardrails

- If `prmerge` reports no PR found for the issue, treat that as a complete answer (nothing to merge). Do not prompt for a manual PR number.
- Mandatory PR review before merge.
- Do not fix failing code/tests in this workflow.
- Delegate implementation changes to `resolve-issue`.
- Document any admin override rationale.
- Never use `/tmp`; use `.tmp/`.
- Never merge with failing CI checks.
- Never merge a PR body that skips `.github/pull_request_template.md` or lacks `./scripts/validate-pr-template.sh` evidence.
- Never treat remote CI as the first time the branch sees the repo's required checks.
- If the remote repository is not enforcing the documented branch protections and required status checks, treat that as an operational risk and report it explicitly.
  </file>
  </skill>
