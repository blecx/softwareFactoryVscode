# Prompt workflow reference

This page is a maintainer-facing reference for the repository's current prompt workflow entrypoints.
It is an index/reference, not a competing normative authority.
The actual workflow rules still live in the prompts themselves, the canonical workflow skills, and the repository-wide guardrail documents.

## Canonical source files

Start with these files when you need to review or change prompt workflow behavior:

- [`../../.github/prompts/execute-github-issues-in-order.prompt.md`](../../.github/prompts/execute-github-issues-in-order.prompt.md) — manual ordered-queue prompt entrypoint for the canonical issue loop.
- [`../../.github/prompts/execute-approved-plan.prompt.md`](../../.github/prompts/execute-approved-plan.prompt.md) — dedicated alias-heavy activation prompt for bounded approved-plan execution.
- [`../../.github/prompts/resume-after-interruption.prompt.md`](../../.github/prompts/resume-after-interruption.prompt.md) — interruption-recovery prompt entrypoint for deterministic re-anchoring.
- [`../../.github/prompts/pr-error-resolve-tactic.prompt.md`](../../.github/prompts/pr-error-resolve-tactic.prompt.md) — fast evidence-first PR/CI error-resolution prompt that narrows failure handling to the cheapest failing gate before wider validation.
- [`../../.github/agents/execute-approved-plan.md`](../../.github/agents/execute-approved-plan.md) and [`../../.github/agents/execute-approved-umbrella.md`](../../.github/agents/execute-approved-umbrella.md) — maintainer-facing agent entrypoints that generalize the bounded-plan and umbrella execution contract beyond issue-specific prompts.
- [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md) — canonical issue → PR → merge path and checkpoint contract.
- [`../../.copilot/skills/resolve-issue-workflow/SKILL.md`](../../.copilot/skills/resolve-issue-workflow/SKILL.md) and [`../../.copilot/skills/interruption-recovery-workflow/SKILL.md`](../../.copilot/skills/interruption-recovery-workflow/SKILL.md) — canonical workflow modules that the prompt entrypoints route back into.
- [`../../.github/copilot-instructions.md`](../../.github/copilot-instructions.md) — repository-wide tool-routing, checkpoint, ADR, and guardrail rules.
- [`AGENT-ENFORCEMENT-MAP.md`](AGENT-ENFORCEMENT-MAP.md) — fastest map from the prompt entrypoints to the governing skills, templates, checkpoints, and ADRs.

## Current prompt workflow surfaces

| Prompt entrypoint | What it is for | How it fits the current workflow graph |
| --- | --- | --- |
| [`execute-github-issues-in-order.prompt.md`](../../.github/prompts/execute-github-issues-in-order.prompt.md) | Manual ordered queue execution with explicit stop gates, GitHub-truth rechecks, and one-issue-at-a-time discipline | Routes into the `workflow` agent and then back into the same canonical `resolve-issue` → `pr-merge` slice path. It is not a second implementation workflow. Use [`@execute-approved-plan`](../../.github/agents/execute-approved-plan.md) instead when the operator has already approved a bounded issue set that may continue automatically. |
| [`execute-approved-plan.prompt.md`](../../.github/prompts/execute-approved-plan.prompt.md) | Dedicated activation surface for alias-heavy approved-plan requests such as `execute the plan` or `run the approved queue` | Routes directly into the specialized [`@execute-approved-plan`](../../.github/agents/execute-approved-plan.md) agent so bounded approved-plan execution does not drift into generic planning behavior. It still reuses the same canonical `resolve-issue` → `pr-merge` slice path. |
| [`resume-after-interruption.prompt.md`](../../.github/prompts/resume-after-interruption.prompt.md) | Deterministic recovery after restart, compaction, timeout, or operator handoff | Re-anchors from `.tmp/github-issue-queue-state.md`, writes `.tmp/interruption-recovery-snapshot.md`, and resumes the currently active workflow instead of inventing a new one. |
| [`pr-error-resolve-tactic.prompt.md`](../../.github/prompts/pr-error-resolve-tactic.prompt.md) | Fast PR/CI failure resolution using exact output parsing, narrow reproductions, and root-cause-first repair sequencing | Routes into the `workflow` agent as a tactical accelerator for PR-error repair. It does not replace the canonical `resolve-issue` → `pr-merge` workflow; it narrows error-resolution behavior so the agent starts with the cheapest failing gate, states the exact failure evidence, and widens validation only after the fast gate passes. |

## Preferred generalized agent entrypoints

- Use [`@execute-approved-plan`](../../.github/agents/execute-approved-plan.md) for any approved bounded GitHub-backed issue set, including a single approved issue or an already-resolved bounded queue.
- Use [`execute-approved-plan.prompt.md`](../../.github/prompts/execute-approved-plan.prompt.md) when the operator uses alias-style language such as `execute the plan` and you want the strongest prompt-level activation surface for the specialized bounded-plan workflow.
- Use [`@execute-approved-umbrella`](../../.github/agents/execute-approved-umbrella.md) when the operator approved an umbrella issue and you need a thin resolver that turns that umbrella into a bounded ordered child issue set before delegating back to `@execute-approved-plan`.
- Treat issue-specific enterprise prompts as historical/narrow wrappers for the concrete issue states they reference; do not generalize future umbrella execution by cloning one-off prompts when the shared agent/skill contract already covers the workflow.

## Shared checkpoints and constraints

- Prompt workflow entrypoints use repo-owned `.tmp/` state, never `/tmp`.
- `.tmp/github-issue-queue-state.md` is the shared checkpoint for queue progress, active issue/branch/PR state, validation evidence, and GitHub truth.
- `resume-after-interruption.prompt.md` pairs that checkpoint with `./.venv/bin/python ./scripts/capture_recovery_snapshot.py` and `.tmp/interruption-recovery-snapshot.md` before implementation, merge, or queue continuation resumes.
- Prompt entrypoints do **not** replace template discipline: issue and PR structure still comes from [`.github/ISSUE_TEMPLATE/feature_request.yml`](../../.github/ISSUE_TEMPLATE/feature_request.yml), [`.github/ISSUE_TEMPLATE/bug_report.yml`](../../.github/ISSUE_TEMPLATE/bug_report.yml), and [`.github/pull_request_template.md`](../../.github/pull_request_template.md).

## Authority reminder

- Use this page to discover the prompt surfaces quickly.
- Use the source files above when you need the real rule text.
- If prompt wording ever appears to conflict with accepted ADRs or the canonical workflow skills, the accepted ADRs and the workflow skills win.
