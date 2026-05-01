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
- **Evidence-First Repair**: After one failed hypothesis, gather fresh evidence before applying another code change. Do not use trial-and-error churn as a repair strategy.

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
- Keep `.tmp/github-issue-queue-state.md` current with `issue_state`, `pr_state`, `ci_state`, `cleanup_state`, and `last_github_truth` before any merge or completion narration.
- Use `./.venv/bin/python ./scripts/noninteractive_gh.py ...` or another pager-free JSON pattern for GitHub polling.
- Prefer `./.venv/bin/python` for repo Python execution; when a justified fallback is necessary, use explicit `python3`, never bare `python`.
- Require explicit success/failure evidence from exit status, structured output, validated artifacts, or exact GitHub metadata. Do not infer success from silence or ambiguous logs.
- If command output, parser behavior, or terminal state is ambiguous, stop and report the ambiguity instead of continuing on guessed state.
- Use `.tmp/`, never `/tmp`.
- Never claim completion without merged-PR evidence and issue-state confirmation on GitHub.

## Execution Procedure

1. Re-anchor from GitHub truth and `.tmp/github-issue-queue-state.md`.
2. Resolve the bounded approved issue set.
3. Publish the remaining queue order and identify the active issue.
4. Before each issue slice, update `.tmp/github-issue-queue-state.md` with the active issue, branch, status, validation evidence, and next gate.
5. Delegate the active slice to the resolve workflow.
6. When the slice becomes ready for merge, delegate to the merge workflow.
7. Poll GitHub checks non-interactively using a bounded wait window; if the result is `pending-timeout`, stop and report the blocker instead of spinning.
8. If checks fail, inspect exact failing metadata, return to the active issue through the canonical resolve workflow, fix the evidenced root cause, rerun required local prechecks, and retry.
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
- current active issue or final completion state,
- validation/CI status,
- and the precise blocker when automatic continuation stops.
