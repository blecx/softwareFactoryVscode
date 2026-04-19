<skill>
<name>pr-merge-workflow</name>
<description>Workflow or rule module for reviewing, validating, and merging GitHub PRs.</description>
<file>
# PR Merge Workflow (Module)

## Objective

Provides context and instructions for the `pr-merge-workflow` skill module.

## When to Use

- A PR is ready or nearly ready and needs merge validation.
- An issue number needs to be resolved through PR discovery and merge.

## When Not to Use

- Do not use this when the current task does not involve concluding, reviewing, or merging PRs.

## Instructions

1. Verify PR is open, mergeable, and not draft using pager-free JSON queries:
   `./.venv/bin/python ./scripts/noninteractive_gh.py pr-view <PR_NUMBER>`
   - Prefer this helper (or another pager-free `gh ... --json ...` pattern) over watch/web flows while you are inside an automation loop.
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
   - Prefer JSON polling over `gh pr checks --watch`; watch/pager UI adds unnecessary terminal churn in repo automation.
   - Refresh `.tmp/github-issue-queue-state.md` from GitHub truth before merge/close narration. Record `issue_state`, `pr_state`, `ci_state`, `cleanup_state`, and `last_github_truth`; `.github/hooks/github-issue-queue-guard.json` / `scripts/github_issue_queue_guard.py` treat that checkpoint as the enforced merge and completion gate.
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
