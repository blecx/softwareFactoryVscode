# Interruption Recovery Workflow

## Objective

Provide a deterministic resume path after a Copilot chat interruption, restart, compaction event, or operator handoff.

## When to Use

- The current issue/PR workflow was interrupted and the next safe action is unclear.
- The agent must re-anchor from repo-owned state instead of guessing from transcript fragments.
- Runtime or MCP-sensitive work needs a fresh local service snapshot before resuming.

## Instructions

1. Read `.tmp/github-issue-queue-state.md` first if it exists.
2. Capture a recovery artifact under `.tmp/` with:
   - `./.venv/bin/python ./scripts/capture_recovery_snapshot.py`
3. For runtime-sensitive work, include service diagnostics with:
   - `./.venv/bin/python ./scripts/capture_recovery_snapshot.py --include-runtime-status`
4. Re-anchor the interrupted task from the snapshot by verifying:
   - current branch
   - `git status --short --branch`
   - active issue/branch/worktree/PR from `.tmp/github-issue-queue-state.md`
   - current GitHub issue/PR/check state
   - `./scripts/factory_stack.py status` output when runtime-sensitive
   - whether the current editor/file/cwd is a valid execution surface or a stray partial `.tmp/queue-worktrees/*` snapshot
5. Update `.tmp/github-issue-queue-state.md` before resuming implementation, merge, cleanup, or queue selection.
6. Do not merge, close, or move to the next issue until checkpoint state and GitHub truth agree.

## Required Artifacts

- `.tmp/github-issue-queue-state.md`
- `.tmp/interruption-recovery-snapshot.md`

## Guardrails

- Use `.tmp/`, never `/tmp`.
- Treat GitHub as the source of truth for issue state, PR state, merge state, and CI/check state.
- Treat runtime snapshots as required when the task touched Docker, MCP, workspace activation, or lifecycle status.
- Treat the current editor/file path as advisory only. If it points under `.tmp/queue-worktrees/*` but the top-level directory is missing repo/worktree markers such as `.git`, `docs/`, or `scripts/`, classify it as a stray partial snapshot and resume from the repository root plus `.tmp/github-issue-queue-state.md` instead.
- Keep the recovery artifact throwaway and free of secrets.
