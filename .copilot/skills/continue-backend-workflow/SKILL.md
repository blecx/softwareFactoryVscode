<skill>
<name>continue-backend-workflow</name>
<description>Orchestrates the continuous loop for backend implementation issues, delegating actual work to core workflows.</description>
<file>
# Continue Backend Workflow

## Objective

## When to Use
- Use this when working on tasks related to continue backend workflow.

## When Not to Use
- Do not use this when the current task does not involve continue backend workflow.

## When to Use
- Use this when working on tasks related to continue backend workflow.

## Objective
Provides context and instructions for the `continue-backend-workflow` skill module.

## Role Contract

**backend orchestration authority** - Manages the iterative issue-to-PR-merge loop specifically for backend tasks. Contains NO domain logic, implementation rules, or coding standards; entirely delegates work execution to canonical core workflows.

## Selection Scope

- Iteratively picks up backend configuration, API, and systems tasks strictly from the backend issue queue.

## Loop Bounds & Stop Conditions

- **Batch Size**: Processes exactly one issue at a time (One Issue = One PR = One Merge).
- **Manual Checkpoint**: Stops and requests manual operator approval before beginning the next issue in the loop.
- **Error Halt**: Stops immediately without advancing if there is a CI failure, workflow error, merge conflict, or blocked PR.
- **Completion**: Breaks the loop gracefully when no backend issues remain.

## Delegation Boundaries

- **Implementation**: MUST defer entirely to `.copilot/skills/resolve-issue-workflow/SKILL.md` to do the actual coding, validation, and PR creation.
- **Merge**: MUST defer entirely to `.copilot/skills/pr-merge-workflow/SKILL.md` to handle the PR merge and workspace cleanup processes.
- **UX/Domain Rules**: DO NOT evaluate or enforce domain constraints here. `resolve-issue-workflow` holds all requirements for handling the implementation details.

## Orchestration Reporting

Use this specific loop-reporting template before pausing for operator approval:

```markdown
### ⚙️ Backend Loop Status
- **Last Resolved Issue:** [#<number> - <title>]
- **Result:** [Merged | Blocked | Failed]
- **Next in Queue:** [#<number> - <title>]
- **Wait State:** ⏸️ Awaiting explicit operator approval to proceed to next issue.
```

## Instructions

- Follow domain guidelines.
</file>
</skill>
