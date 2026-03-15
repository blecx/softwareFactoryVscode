<skill>
<name>continue-phase-2-workflow</name>
<description>Orchestrates the continuous loop for Phase 2 implementation issues, delegating actual work to core workflows.</description>
<file>
# Continue Phase 2 Workflow

## Objective

## When to Use
- Use this when working on tasks related to continue phase 2 workflow.

## When Not to Use
- Do not use this when the current task does not involve continue phase 2 workflow.

## When to Use
- Use this when working on tasks related to continue phase 2 workflow.

## Objective
Provides context and instructions for the `continue-phase-2-workflow` skill module.

## Role Contract

**phase-2 orchestration authority** - Manages the iterative issue-to-PR-merge loop specifically for Phase 2 tasks. Contains NO domain logic, implementation rules, or coding standards; entirely delegates work execution to canonical core workflows.

## Selection Scope

- Iteratively picks up Phase 2 integration tasks (e.g., following the sequential backlog or issues labeled for Phase 2).

## Loop Bounds & Stop Conditions

- **Batch Size**: Processes exactly one issue at a time (One Issue = One PR = One Merge).
- **Manual Checkpoint**: Stops and requests manual operator approval before beginning the next issue in the loop.
- **Error Halt**: Stops immediately without advancing if there is a CI failure, workflow error, merge conflict, or blocked PR.
- **Completion**: Breaks the loop gracefully when no more Phase 2 issues remain.

## Delegation Boundaries

- **Implementation**: MUST defer entirely to `.copilot/skills/resolve-issue-workflow/SKILL.md` to do the actual coding, validation, and PR creation.
- **Merge**: MUST defer entirely to `.copilot/skills/pr-merge-workflow/SKILL.md` to handle the PR merge and workspace cleanup processes.
- **UX/Domain Rules**: DO NOT evaluate or enforce UX checks, small-slice rules, or domain constraints here. Trust that `resolve-issue-workflow` will pull `.copilot/skills/ux-delegation-policy/SKILL.md` and enforce rules on its own.

## Orchestration Reporting

Use this specific loop-reporting template before pausing for operator approval:

```markdown
### 🔄 Phase 2 Loop Status
- **Last Resolved Issue:** [#<number> - <title>]
- **Result:** [Merged | Blocked | Failed]
- **Next in Queue:** [#<number> - <title>]
- **Wait State:** ⏸️ Awaiting explicit operator approval to proceed to next issue.
```

## Instructions

- Follow domain guidelines.
</file>
</skill>
