<skill>
<name>tutorial-review-workflow</name>
<description>Skill for tutorial review workflow</description>
<file>
# Tutorial Review Workflow Skill

## Objective
Strict, read-only checklist for auditing existing tutorials to ensure accuracy and freshness against the current codebase without making destructive changes.

## Risk Profile
**Auto-Approvable (Safe)** - This skill assumes a zero-write boundary. 

## When to Use
- The user requests an audit or validation of existing tutorials.
- Checking tutorial accuracy or standard compliance against the current architecture.
- Identifying stale documentation.


## When Not to Use
- Do not use this when not working directly on tutorial review workflow.
## Instructions
1. **Target Identification:** Read the specific tutorial or documentation set requested by the operator.
2. **Codebase Correlation:** Verify every code snippet properly against current `apps/api` and `client/` sources using file reads and search.
3. **Format Validation:** Check that document structure follows the team's markdown conventions.
4. **Report Generation:** Produce a strict pass/fail discrepancy report highlighting:
   - Outdated API paths or arguments.
   - Missing dependencies or incorrect imports.
   - Conceptual gaps compared to runtime reality.

## Constraints & Guardrails
- **STRICTLY READ-ONLY:** Never use tools to edit or overwrite files.
- Produce evidence and line-number citations for every discrepancy.
- If everything passes, output a clean confirmation of accuracy.
</file>
</skill>