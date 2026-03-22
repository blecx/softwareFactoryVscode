---
description: blecs extension - execute the repeatable backend issue queue to PR to merge loop.
---

# blecs.queue-backend

Run `/queue-backend` for iterative backend implementation work.

This is a thin discoverability wrapper.
For actual workflow loops, stop conditions, and reporting formats, you MUST read and follow `.copilot/skills/backend-queue-workflow/SKILL.md`.

Do not apply arbitrary domain rules here; this agent delegates entirely to core `resolve-issue` and `pr-merge` workflows.

User request:
$ARGUMENTS
