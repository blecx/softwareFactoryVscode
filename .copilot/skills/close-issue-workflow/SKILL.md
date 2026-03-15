<skill>
<name>close-issue-workflow</name>
<description>Workflow or rule module for closing GitHub issues with verified outcome, template-backed comments, and traceability.</description>
<file>
# Close Issue Workflow (Module)

## Objective
Provides context and instructions for the `close-issue-workflow` skill module.

Use this skill as the canonical implementation source for `close-issue`.

## When to Use

- A merged PR or explicit maintainer decision has established the issue outcome.
- An issue should be closed as completed or not planned with traceable evidence.

## When Not to Use
- Do not use this when the current task does not involve close issue workflow.

## Instructions

1. Verify the issue exists and is still open.
2. Verify the outcome evidence:
   - completed: merged PR and default-branch landing,
   - not planned: documented rationale and any canonical duplicates/links.
3. Choose the correct close template and reason.
4. Prepare concrete closure data under `.tmp/` when needed.
5. Dry-run the close template, then post the final close action.
6. Verify the issue is closed and the closing comment is present.

## Required Evidence

- Issue number
- Outcome reason
- PR number or merge commit for completed work when available
- Validation or rationale notes suitable for the closing comment

## Guardrails

- Never close by guessing.
- Do not implement code or refactor in this workflow.
- Use `.tmp/`, never `/tmp`.
- Never stage `projectDocs/` or `configs/llm.json`.
- For UI/UX-affecting issues, include closure evidence consistent with the canonical UX delegation policy.

## Completion Contract

Return a concise result that states:

- issue number,
- verified outcome,
- close reason,
- PR/commit traceability,
- final close status or blocker.
</file>
</skill>
