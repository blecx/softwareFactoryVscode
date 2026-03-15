<skill>
<name>ux-delegation-policy</name>
<description>Workflow or rule module extracted from .copilot/skills/ux-delegation-policy/SKILL.md</description>
<file>
# UX Skill: Delegation Policy (Mandatory)

## Objective
Provides context and instructions for the `ux-delegation-policy` skill module.

## When to Use
- Use this when working on tasks related to ux delegation policy.

## When Not to Use
- Do not use this when the current task does not involve frontend UI, styling, or ux delegation policy.

## Instructions
Canonical policy source: This file is the single source of truth for UX delegation rules across governance prompts and workflow prompts.

- Non-UX agents must not make final navigation/graphical UX decisions independently.
- If a change affects UI, navigation, responsive behavior, or visual grouping, consult `blecs-ux-authority`.
- Block implementation/review completion until UX decision is `PASS` or required `CHANGES` are applied.

Trigger matrix (consultation REQUIRED):
- New/updated screens, dialogs, panels, menus
- Navigation, routing, or information architecture changes
- Responsive/layout breakpoint behavior changes
- Interaction model or artifact grouping changes
- Accessibility-relevant interaction changes (focus, labels, keyboard paths)

Anti-bypass rule:
- Ambiguous scope defaults to consultation REQUIRED.
</file>
</skill>