---
name: blecs-workflow-authority
description: "blecs workflow authority: keeps project workflow truth and provides normalized context packets for other agents."
---

# blecs Workflow Authority Skill

## Objective
Maintains and provides the canonical workflow source of truth for the repository and downstream agent runs. It keeps project workflow truth and provides normalized context packets for other agents.

## When to Use
- You need to determine the correct workflow pipeline or governance rules for a task.
- You are orchestrating tasks that require workflow truth and context synchronization between implementation, review/merge, or UX authority agents.
- You need to generate a workflow context packet for another downstream agent.

## When Not to Use
- You are making direct UI/UX design decisions (route to `blecs-ux-authority` instead).
- You are implementing code that does not depend on project workflows or pipeline constraints.

## Required Sources
- `docs/WORK-ISSUE-WORKFLOW.md`
- `.github/copilot-instructions.md`
- `.github/workflows/ci.yml`

## Constraints
- Produce compact workflow context packets for implementation agents, review/merge agents, and the blecs UX Authority Agent.
- Keep constraints synchronized (validation commands, PR evidence, hygiene, DDD boundaries).
- Do not design UX directly; route design decisions to `blecs-ux-authority`.

## Completion Contract
Return:
- `WORKFLOW_PACKET:` summary
- `MUST_RULES:` non-negotiable process constraints
- `UX_INPUTS:` workflow signals relevant for UX decisions
- `VALIDATION:` exact commands and evidence expectations
