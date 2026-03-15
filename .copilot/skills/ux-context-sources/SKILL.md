<skill>
<name>ux-context-sources</name>
<description>Workflow or rule module extracted from .copilot/skills/ux-context-sources/SKILL.md</description>
<file>
# UX Skill: Context Sources

## Objective
Provides context and instructions for the `ux-context-sources` skill module.

## When to Use
- Use this when working on tasks related to ux context sources.

## When Not to Use
- Do not use this when the current task does not involve frontend UI, styling, or ux context sources.

## Instructions
Derive product intent from:

- `README.md`
- `docs/development.md`
- `docs/WORK-ISSUE-WORKFLOW.md`
- active UI code under `../maestro-client/client/`

Always summarize inferred intent before proposing navigation/layout changes.

Source precedence for conflicts:
1. Implemented runtime/CI behavior
2. Active code paths and tests
3. Current workflow documentation
4. Historical planning notes

Confidence rule:
- If confidence is low due to missing evidence, record it as a requirement gap.
</file>
</skill>