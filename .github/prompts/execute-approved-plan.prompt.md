---
description: "Route explicit approved-plan requests like execute the plan, continue the plan, or run the approved queue into the specialized execute-approved-plan workflow instead of generic planning drift."
name: "Execute Approved Plan"
argument-hint: "Approved issue set, umbrella issue, queue checkpoint, or optional clarification for the bounded plan"
agent: "execute-approved-plan"
model: "GPT-5 (copilot)"
---

## Objective

Activate the specialized approved-plan workflow when the operator is clearly asking to execute a bounded approved issue set.

This prompt exists to reduce routing drift for phrases such as `execute the plan`, `continue the plan`, `run the approved queue`, `work through the approved backlog`, and `finish the approved issue set`.

It is an activation surface only. It does **not** define a second implementation, repair, or merge workflow.

## When to Use

- The operator says `execute the plan`, `continue the plan`, `run the approved queue`, `work through the approved backlog`, or `finish the approved issue set`.
- A finite approved GitHub-backed issue set, a single approved issue, an umbrella-derived child issue set, or a published queue checkpoint is already known.
- You need the specialized `execute-approved-plan` orchestration wrapper rather than generic planning or ad-hoc coding behavior.

## When Not to Use

- The task is a single ad-hoc implementation request with no approved bounded issue set.
- The request is only to create issues.
- More than one plausible approved plan exists and the operator has not clarified which bounded set is approved.

## Constraints

1. Route into [`@execute-approved-plan`](../agents/execute-approved-plan.md), not a generic planning response.
2. Keep [`../../docs/WORK-ISSUE-WORKFLOW.md`](../../docs/WORK-ISSUE-WORKFLOW.md) and [`../copilot-instructions.md`](../copilot-instructions.md) as the authority source.
3. Reuse the same canonical `resolve-issue` → `pr-merge` slice path; do **not** create a second implementation workflow.
4. Keep `.tmp/github-issue-queue-state.md` and `.tmp/interruption-recovery-snapshot.md` as the shared checkpoint/recovery surfaces.
5. If the approved bounded set is ambiguous, ask for clarification instead of falling back to generic assistant behavior.

## Required Working Method

1. Treat the request as workflow orchestration, not generic planning chatter.
2. Confirm that a bounded approved issue set is unambiguous.
3. Delegate execution to the specialized `execute-approved-plan` workflow.
4. Keep recovery, checkpoint, validation, and merge behavior on the existing canonical workflow surfaces.

## Completion Criteria

This prompt is complete only when the request is routed into the specialized `execute-approved-plan` workflow or stopped for explicit clarification about which approved bounded issue set should run.
