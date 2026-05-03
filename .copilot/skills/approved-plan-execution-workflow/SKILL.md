---
name: approved-plan-execution-workflow
description: "Execute a bounded approved GitHub-backed issue plan. Use when the operator says execute the plan, continue the plan, run the approved queue, work through the approved backlog, or finish the approved issue set."
argument-hint: "Approved issue set, umbrella issue, or bounded queue"
---

# Approved Plan Execution Workflow

## Objective

Provides context and instructions for the `approved-plan-execution-workflow` skill module.

This is the generic executor for any approved bounded GitHub-backed issue set,
including a single approved issue, an umbrella-derived child issue set, an
explicit approved issue list, or an already-published bounded queue.

## When to Use

- A user says execute the plan, continue the plan, run the approved queue, work through the approved backlog, or finish the approved issue set.
- A finite GitHub-backed issue set, umbrella issue, or already-published queue should be executed end-to-end.
- The operator wants automatic continuation across slices until the bounded set is complete or a true blocker appears.

## When Not to Use

- The task is only one issue-to-PR slice; use `.copilot/skills/resolve-issue-workflow/SKILL.md` instead.
- The task is only to create issues; use `.copilot/skills/issue-creation-workflow/SKILL.md`.
- More than one plausible plan or issue set exists and the operator has not clarified which one is approved.
- The requested loop would exceed the explicitly approved issue set.

## Role Contract

**approved plan execution wrapper** — Manages a bounded, explicitly approved, GitHub-backed issue set end-to-end. This skill owns plan-source resolution, ordering, stop conditions, and repetition only. The single source of truth for issue-to-merge mechanics remains the canonical `resolve-issue` → `pr-merge` slice path.

## Required Sources

- `.copilot/skills/a2a-communication/SKILL.md`
- `.copilot/skills/resolve-issue-workflow/SKILL.md`
- `.copilot/skills/pr-merge-workflow/SKILL.md`
- `.copilot/skills/interruption-recovery-workflow/SKILL.md`
- `docs/WORK-ISSUE-WORKFLOW.md`
- `.github/copilot-instructions.md`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- `docs/architecture/ADR-005-Strong-Templating-Enforcement.md`
- `docs/architecture/ADR-006-Local-CI-Parity-Prechecks.md`

## Plan Resolution Rules

1. Resolve the approved plan from one of these sources only:
   - an explicit issue list provided by the operator;
   - an umbrella issue whose child issue set is explicit on GitHub;
   - an already-published queue stored in `.tmp/github-issue-queue-state.md`.
2. A single approved GitHub issue is a valid bounded issue set of size one; treat it as an approved plan source without redefining it as an umbrella.
3. If multiple plausible plans exist, stop and ask which plan or issue set is approved. Do not guess.
4. If the request is vague (`execute the plan`) and there is no unambiguous bounded issue set, ask a clarifying question before starting.
5. Never continue beyond the finite approved issue set named by the operator.

## Loop Bounds and Stop Conditions

- **Batch Size**: Processes one issue at a time internally (One Issue = One PR = One Merge), but keeps moving across the approved bounded set without re-asking between slices.
- **Automatic Continuation**: Treat the operator request as approval for the full bounded issue set, not just the first slice.
- **Error Halt**: Stop immediately on CI failures that are not yet fixed, merge conflicts, blocked PRs, template violations, missing validation evidence, workflow ambiguity, or architecture conflicts.
- **Polling Rule**: Do not stop merely because CI is pending, but also do not wait indefinitely. Use bounded non-interactive polling (prefer `./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks <PR_NUMBER> --wait --timeout-seconds 600`) and continue automatically only when checks reach terminal success within that window.
- **Pending-Timeout Halt**: If CI is still pending after the 10-minute bounded wait window, record the still-pending GitHub truth in `.tmp/github-issue-queue-state.md`, report a precise `pending-timeout` blocker, and stop so a later resume can re-anchor safely.
- **Completion**: Break the loop only when every issue in the approved set is merged and GitHub-verified closed, or when a true blocker prevents safe continuation.
- **Evidence-First Repair**: After a failed validation or CI/check, the next repair step must quote the exact failing command/check, the relevant error text, and the suspected root cause from fresh evidence before another code change is attempted.
- **Default Fast Repair Ladder**: For PR-body/template errors, local validation failures, or GitHub CI/check failures inside the queue, use the repository default from `.github/prompts/pr-error-resolve-tactic.prompt.md`: parse exact current output first, inspect the exact failing file/test/method/check when named, reproduce the cheapest failing gate first, and widen validation only after the narrower gate passes.
- **No Guessing or Broad-Scan Drift**: Do not start repair with broad repo scans, parity-first reruns, stale checkpoint memory, or guessed root causes when current failure evidence is already specific.
- **No Trial-and-Error Churn**: After one failed hypothesis, gather fresh evidence before applying another code change. Do not use trial-and-error churn as a repair strategy, and do not make a second repair change without new evidence.

## Delegation Boundaries

- **Implementation**: MUST defer to `.copilot/skills/resolve-issue-workflow/SKILL.md`.
- **Merge**: MUST defer to `.copilot/skills/pr-merge-workflow/SKILL.md`.
- **Recovery**: MUST use `.copilot/skills/interruption-recovery-workflow/SKILL.md` after interruption, compaction, timeout, or continuity loss.
- **Issue drafting**: MUST defer to `.copilot/skills/issue-creation-workflow/SKILL.md` if the plan is incomplete and new issues are required.
- **Umbrella resolution**: Specialized umbrella wrappers may resolve an umbrella into a bounded child issue set, but they MUST still delegate execution back into this skill rather than defining a second execution loop.
- **Scoped manual queues**: `queue-backend` and `queue-phase-2` are manual-approval wrappers over the same canonical slice path, not alternate implementations of plan execution.
- **Legacy loops**: DO NOT use legacy shell/Python workflow loops.

## Guardrails

- Only continue queue work backed by template-compliant GitHub issues.
- Treat `.github/pull_request_template.md` and `./scripts/validate-pr-template.sh` as mandatory PR handoff gates.
- Require local CI-equivalent validation from `.github/workflows/ci.yml` before handing a slice from resolve to merge.
- Treat the execution surface as part of the approved-plan contract: every active issue must run from its own dedicated branch and registered isolated worktree, typically under `.tmp/queue-worktrees/`, and must not reuse the dirty primary checkout or another issue's worktree.
- Before any implementation, validation, merge narration, or automatic continuation step, confirm the active issue number, branch, and worktree path all agree with `.tmp/github-issue-queue-state.md`.
- Keep `.tmp/github-issue-queue-state.md` current with `issue_state`, `pr_state`, `ci_state`, `cleanup_state`, and `last_github_truth` before any merge or completion narration.
- Record `active_worktree` in `.tmp/github-issue-queue-state.md` alongside `active_issue`, `execution_lease_id`, and `active_branch` so the canonical resume point preserves the exact per-issue execution surface.
- Treat `./.venv/bin/python ./scripts/local_ci_parity.py --level merge` as the canonical local PR-readiness evidence for slice handoff/readiness narration.
- Use `./.venv/bin/python ./scripts/noninteractive_gh.py ...` or another pager-free JSON pattern for GitHub polling.
- Require `last_github_truth` to capture the exact helper command(s), selector(s), and current result summary behind the current queue checkpoint.
- Refresh GitHub truth immediately before readiness, merge, queue-advance, or blocker narration; do not continue from memory, terminal silence, or stale checkpoint evidence.
- Treat same-issue concurrent-session execution surface collisions as blockers. If the `execution_lease_id` or branch/worktree suffix belongs to another session, stop and request re-anchor, handoff, or a fresh surface.
- When a PR exists, require the GitHub `headRefName`, the current local branch, and checkpoint `active_branch` to agree before continuing; treat any mismatch as a blocker that requires re-anchor.
- Prefer `./.venv/bin/python` for repo Python execution; when a justified fallback is necessary, use explicit `python3`, never bare `python`.
- Require explicit success/failure evidence from exit status, structured output, validated artifacts, or exact GitHub metadata. Do not infer success from silence or ambiguous logs.
- If command output, parser behavior, or terminal state is ambiguous, stop and report the ambiguity instead of continuing on guessed state.
- Use `.tmp/`, never `/tmp`.
- Never claim completion without merged-PR evidence and issue-state confirmation on GitHub.

## Execution Procedure

1. Re-anchor from GitHub truth and `.tmp/github-issue-queue-state.md`.
2. Resolve the bounded approved issue set.
3. Publish the remaining queue order and identify the active issue.
4. Before each issue slice, update `.tmp/github-issue-queue-state.md` with the active issue, branch, worktree path, status, validation evidence, and next gate.
5. Delegate the active slice to the resolve workflow.
6. When the slice becomes ready for merge, delegate to the merge workflow.
7. Poll GitHub checks non-interactively using a bounded wait window; if the result is `pending-timeout`, stop and report the blocker instead of spinning.
8. If checks fail, or if fresh GitHub truth shows a PR head-branch mismatch against the local/checkpoint branch provenance, inspect the exact metadata, return to the active issue through the canonical resolve workflow, reproduce the cheapest local failing gate, fix the evidenced root cause, rerun the narrow prechecks, and retry wider validation only after those pass.
9. After merge, verify GitHub issue closure and queue checkpoint evidence, then advance automatically to the next approved issue.
10. If interrupted, capture `.tmp/interruption-recovery-snapshot.md`, re-anchor, and resume from GitHub truth instead of guessing.

## Orchestration Reporting

Use this reporting template while the loop is active:

```markdown
### ✅ Approved Plan Execution Status

- **Approved Queue:** [#<number>, #<number>, ...]
- **Last Resolved Issue:** [#<number> - <title>]
- **Result:** [Merged | Blocked | Failed]
- **Current Active Issue:** [#<number> - <title> | none]
- **Wait State:** [▶️ Continuing automatically | ⛔ Blocked]
```

## Output Contract

Return:

- approved queue order,
- last resolved issue,
- active branch/worktree pair,
- current active issue or final completion state,
- validation/CI status,
- and the precise blocker when automatic continuation stops.
