---
description: "Re-anchor an interrupted issue/PR workflow from repo-owned checkpoint state, live GitHub truth, and optional runtime diagnostics."
name: "Resume After Interruption"
argument-hint: "Optional: issue number, PR number, runtime-sensitive yes/no, or alternate .tmp snapshot path"
agent: "workflow"
model: "GPT-5 (copilot)"
---

## Objective

Resume interrupted issue work without guessing.

When continuity is lost because of compaction, restart, timeout, tool uncertainty, or operator handoff, rebuild the next safe action from repo-owned `.tmp` state plus fresh GitHub truth.

## When to Use

- A chat session was interrupted, compacted, restarted, or re-attached.
- The current issue/PR state is unclear and needs deterministic recovery.
- The task touched runtime or MCP services and needs a quick topology/status snapshot before resuming.

## Constraints

1. Use `.tmp/`, never `/tmp`.
2. Treat GitHub as the source of truth for issue state, PR state, merge state, and CI/check state.
3. Read `.tmp/github-issue-queue-state.md` before deciding what happens next.
4. Capture or refresh `.tmp/interruption-recovery-snapshot.md` with:
   - `./.venv/bin/python ./scripts/capture_recovery_snapshot.py`
5. Add `--include-runtime-status` when the interrupted task touched runtime, Docker, MCP, or workspace lifecycle infrastructure.
   - The runtime-sensitive path captures `./scripts/factory_stack.py status` output inside `.tmp/interruption-recovery-snapshot.md`.
6. Do not merge, close, or start the next issue until branch state, queue state, GitHub truth, and any needed runtime state all agree.

## Required Working Method

1. Read `.tmp/github-issue-queue-state.md` if it exists.
2. Capture `.tmp/interruption-recovery-snapshot.md` with `./.venv/bin/python ./scripts/capture_recovery_snapshot.py`.
3. If the task touched runtime/MCP infrastructure, rerun the helper with `--include-runtime-status`.
4. Re-anchor from the snapshot by checking:
   - current branch
   - working tree state
   - active issue number
   - active PR number/state
   - current CI/check state
   - runtime/service state when applicable
5. Update `.tmp/github-issue-queue-state.md` before continuing implementation, merge, cleanup, or queue selection.
6. Continue only the currently active issue unless the operator has explicitly approved moving to the next one.

## Output Format

### Re-anchor summary

- branch and working tree state
- active issue and PR
- whether GitHub truth matches the checkpoint

### Queue checkpoint

- whether `.tmp/github-issue-queue-state.md` was found or updated
- key fields that matter for resumption

### Runtime / service snapshot

- whether runtime diagnostics were captured
- the relevant service/topology conclusion or why it was skipped

### Next safe action

- the exact next step
- whether the workflow is safe to continue or blocked

## Completion Criteria

The recovery is complete only when:

- `.tmp/interruption-recovery-snapshot.md` exists under `.tmp/`
- the current branch and working tree state are known
- the active issue/PR and CI/check truth were refreshed from GitHub when applicable
- runtime/service state was captured for runtime-sensitive work
- `.tmp/github-issue-queue-state.md` reflects the resumed state before work continues
