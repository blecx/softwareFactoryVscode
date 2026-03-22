---
description: blecs extension - execute the repeatable Phase 2 issue queue to PR to merge loop.
---

# blecs.queue-phase-2

Run `/queue-phase-2` for iterative Phase 2 integration work.

This is a thin discoverability wrapper.
For actual workflow loops, stop conditions, and reporting formats, you MUST read and follow `.copilot/skills/phase-2-queue-workflow/SKILL.md`.

Do not apply arbitrary domain rules here; this agent delegates entirely to core `resolve-issue` and `pr-merge` workflows.

User request:
$ARGUMENTS
