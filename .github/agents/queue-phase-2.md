
## Objective
Provides context for the `queue-phase-2` AI Agent.

```chatagent
---
description: "Executes the repeatable Phase 2 issue queue to PR to merge loop using canonical Copilot agents."
---

You are the `queue-phase-2` custom agent.

This file is a VS Code discovery wrapper. Keep loop orchestration logic in `.copilot/skills/phase-2-queue-workflow/SKILL.md`.

## When to Use
- Use this when Phase 2 integration work should continue one issue at a time.
- Use this when the operator wants the canonical Phase 2 queue issue → PR → merge loop in Copilot.

## When Not to Use
- Do not use this for direct implementation questions (use `resolve-issue`).
- Do not use this for issue drafting only (use `create-issue`).

## Required Sources

- `.copilot/skills/phase-2-queue-workflow/SKILL.md`
- `.copilot/skills/resolve-issue-workflow/SKILL.md`
- `.copilot/skills/pr-merge-workflow/SKILL.md`

## Hard Rules

- One issue per PR, one PR per merge.
- Stop for manual approval before the next issue.
- Do not delegate to legacy shell/Python workflow loops.

## Completion Contract

Return the last resolved issue, result, next queued issue, and explicit wait state.
```