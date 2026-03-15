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
1. Verify PR is open, mergeable, and not draft using:
   `gh pr status` and `gh pr view`
2. Confirm required CI/CD checks are green by explicitly running:
   `gh pr checks <PR_NUMBER>`
3. Merge with squash and delete branch:
   `gh pr merge <PR_NUMBER> --squash --delete-branch`
4. Comment and close linked issue (if needed).
5. Clean transient `.tmp` files MANDATORILY using:
   `rm -f .tmp/pr-body-<issue-number>.md .tmp/issue-<issue-number>-*.md`
6. Sync local `main` via `git checkout main && git pull` and verify final state.

## Required Checks
- Choose the correct repo and validation gate before merge.
- Require real validation evidence in the PR body.
- For UI/UX-affecting changes, require recorded UX authority resolution.
- Capture merge metrics when tooling supports it.

## Guardrails
- If `prmerge` reports no PR found for the issue, treat that as a complete answer (nothing to merge). Do not prompt for a manual PR number.
- Mandatory PR review before merge.
- Do not fix failing code/tests in this workflow.
- Delegate implementation changes to `resolve-issue`.
- Document any admin override rationale.
- Never use `/tmp`; use `.tmp/`.
- Never merge with failing CI checks.
</file>
</skill>
