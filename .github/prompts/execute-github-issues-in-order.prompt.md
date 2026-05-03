---
description: "Run GitHub issues in canonical repo order with interruption-safe checkpoints, one-issue-per-PR discipline, GitHub-truth verification, and repo-owned .tmp state."
name: "Execute GitHub Issues In Order"
argument-hint: "Optional: starting issue, label filter, queue type, stop condition, or approved ordering override"
agent: "workflow"
model: "GPT-5 (copilot)"
---

## Objective

Execute GitHub issues in the repository's canonical order without workflow drift.

You cannot assume the session will remain uninterrupted. Instead, guarantee **deterministic recovery and ordered resumption** by re-anchoring from GitHub truth and a repo-owned `.tmp` checkpoint whenever continuity is lost.

## When to Use

- The user wants GitHub issues executed in the correct order.
- The user wants a one-issue-at-a-time issue → PR → merge loop.
- The user wants interruption-safe queue work with clear stop gates.
- The user allows subagents when they help preserve workflow discipline.

This prompt is the manual ordered-queue variant. For a bounded approved issue
set that should continue automatically within the set, use
`@execute-approved-plan` instead.

## When Not to Use

- The task is only to create a new issue.
- The task is only to merge or close an already-ready PR.
- The work is not tied to GitHub issues.
- The user wants ad-hoc coding outside the canonical workflow.

## Inputs

- Optional starting issue number.
- Optional label, milestone, or scope filter.
- Optional queue preference such as `backend`, `phase-2`, or an explicit approved issue list.
- Optional stop condition such as `one issue`, `until blocked`, or `N issues`.
- Optional approved override to the default repository ordering.

## Constraints

1. Use [the canonical workflow](../../docs/WORK-ISSUE-WORKFLOW.md) and [repo guardrails](../copilot-instructions.md) as binding policy.
2. Use GitHub as the source of truth for:
   - issue state
   - PR state
   - CI/check state
   - merge state
3. Enforce **one issue = one PR = one merge**.
4. Select the next issue in canonical order unless the user explicitly approves a different order:
   - backend-first
   - then lowest issue number
5. Never edit on `main`. Create a dedicated branch and use a dedicated registered worktree for the active issue before implementation.
6. Use `.tmp/`, never `/tmp`.
7. Maintain a checkpoint file at `.tmp/github-issue-queue-state.md` and update it at every major state change.
8. Treat interruptions as expected, not exceptional. After any interruption, timeout, compaction, or tool uncertainty, re-anchor before continuing by checking:
   - current branch
   - git status
   - active issue number
   - active PR number/state
   - current CI/check state
   - `.tmp/github-issue-queue-state.md`
   - `.tmp/interruption-recovery-snapshot.md` captured via `.github/prompts/resume-after-interruption.prompt.md` or `./.venv/bin/python ./scripts/capture_recovery_snapshot.py`
9. Use the correct templates:
   - [issue templates](../ISSUE_TEMPLATE/feature_request.yml)
   - [PR template](../pull_request_template.md)
10. Run the required local validation before opening or finalizing a PR:
    - `./.venv/bin/python ./scripts/local_ci_parity.py`
11. Stop immediately on:
    - CI failures
    - merge conflicts
    - template violations
    - missing validation evidence
    - workflow ambiguity
    - missing operator approval for the next issue
12. Never claim an issue is complete until GitHub confirms the PR is merged and the linked issue state is correct.
13. Subagents are allowed, but the parent workflow must remain accountable for order and continuity:
    - use read-only exploration subagents for discovery only

- use `resolve-issue` for implementation
- use `pr-merge` for merge validation and merge
- use `queue-backend` or `queue-phase-2` only after the current issue is fully merged or intentionally blocked

14. Do not start the next issue automatically after a merge. Require an explicit operator checkpoint and approval.

## Required Working Method

1. Discover the candidate issue set from GitHub.
2. Publish the ordered queue and explain why that order is valid.
3. Select only the first executable issue.
4. Write or update `.tmp/github-issue-queue-state.md` with at least:

   ```md
   # GitHub issue queue state

   - active_issue: <number>
   - active_branch: <branch>
   - active_worktree: <absolute path>
   - active_pr: <number or none>
   - status: selected | implementing | validating | pr-open | blocked | merged
   - last_validation: <command or none>
   - next_gate: <what must happen next>
   - blocker: <none or explanation>
   ```

5. Execute the current issue only.
   - Use the same canonical `resolve-issue` → `pr-merge` slice path as every
     other repository workflow.
6. Before any handoff, interruption recovery, or completion claim, re-check GitHub truth.
   - If continuity was lost, capture `.tmp/interruption-recovery-snapshot.md` before resuming.
7. End each iteration with one of these states only:
   - `blocked`
   - `waiting-for-approval`
   - `ready-for-pr-merge`
   - `merged-and-closed`

## Output Format

Produce responses in this structure:

### Queue order

- ordered issue list with the rule used to choose the order
- explicit note of any user-approved override

### Active issue

- issue number and title
- why it is the correct next item
- branch name
- PR status

### Checkpoint

- whether `.tmp/github-issue-queue-state.md` was created or updated
- current state from that file
- last validation command run

### Stop gate

- exactly one of:
  - `blocked`
  - `waiting-for-approval`
  - `ready-for-pr-merge`
  - `merged-and-closed`
- the precise next action required

## Completion Criteria

The prompt is complete only when all of the following are true:

- the queue order is derived from GitHub truth and stated explicitly
- only the correct next issue is acted on
- `.tmp/github-issue-queue-state.md` exists and reflects the current state
- any interruption is handled by re-anchoring instead of guessing
- the workflow stops at a safe gate instead of drifting into the next issue
- no completion claim is made without merged-PR and issue-state confirmation on GitHub
