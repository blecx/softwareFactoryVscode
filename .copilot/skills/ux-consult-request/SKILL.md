<skill>
<name>ux-consult-request</name>
<description>Workflow or rule module extracted from .copilot/skills/ux-consult-request/SKILL.md</description>
<file>
# UX Skill: Consult Request Template

## Objective
Provides context and instructions for the `ux-consult-request` skill module.

## When to Use
- Use this when working on tasks related to ux consult request.

## When Not to Use
- Do not use this when the current task does not involve frontend UI, styling, or ux consult request.

## Instructions
Use this payload for UX consultations:

- Issue/PR context
- User workflow goal
- Changed files
- Current behavior
- Proposed behavior
- Constraints (tech/process)
- Acceptance criteria
- Known risks
- Evidence links/paths (mockups, screenshots, PR sections)

Expected response:
- `UX_DECISION: PASS|CHANGES`
- `Requirement Check:`
- `Requirement Gaps:`
- `Risk Notes:`
- Required changes (if any)

Preferred request format:

```
ISSUE_PR_CONTEXT:
USER_GOAL:
CHANGED_FILES:
CURRENT_BEHAVIOR:
PROPOSED_BEHAVIOR:
ACCEPTANCE_CRITERIA:
CONSTRAINTS:
KNOWN_RISKS:
EVIDENCE_PATHS:
```
</file>
</skill>