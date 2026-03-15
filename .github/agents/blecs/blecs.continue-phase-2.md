---
description: blecs extension - execute the repeatable phase-2 issue to PR to merge loop.
---

# blecs.continue-phase-2

Run `/continue-phase-2` process for iterative integration work.

This is a thin discoverability wrapper.
For actual workflow loops, stop conditions, and reporting formats, you MUST read and follow `.copilot/skills/continue-phase-2-workflow/SKILL.md`.

Do not apply arbitrary domain rules here; this agent delegates entirely to core `resolve-issue` and `pr-merge` workflows.

User request:
$ARGUMENTS
