<skill>
<name>blecs-ux-authority</name>
<description>blecs UX authority: mandatory consultation for navigation, graphical design, responsive behavior, modern React/Vite/Tailwind UI patterns, and UX/a11y review.</description>
<file>
# Blecs Ux Authority

## Objective

## When to Use
- Use this when working on tasks related to blecs ux authority.

## When Not to Use
- Do not use this when the current task does not involve frontend UI, styling, or blecs ux authority.

## When to Use
- Use this when working on tasks related to blecs ux authority.

## Objective
Provides context and instructions for the `blecs-ux-authority` skill module.

---
description: "blecs UX authority: mandatory consultation for navigation, graphical design, responsive behavior, modern React/Vite/Tailwind UI patterns, and UX/a11y review."
---

# blecs UX Authority Skill

This skill defines the canonical constraints for UI/UX and modern Web App Generation code. 

You are the single authority for:
- Navigation and information architecture
- Graphical layout and responsive behavior
- Modern styling (React, Vite, Tailwind CSS, shadcn/ui patterns)
- Component generation standards and accessibility UX requirements

## Required Consultation Scope

Any AI assistant or agent that plans, implements, reviews, or merges changes that affect UI/UX must consult this skill first.
Consultation is mandatory for navigation structure changes, new/updated screens or panels, responsive layout changes, component grouping and interaction model changes, and PR reviews touching UX-sensitive paths.

## 1. Core Rules & Navigation Architecture

1. Produce a **navigation plan first** (IA/sitemap + primary/secondary nav model).
2. Reject "one tile per object" anti-patterns when object interactions require grouped flows.
3. Enforce mobile-first responsive behavior with full-width usage and no cut-off content.
4. Run an explicit requirement check (navigation, responsive, grouping, a11y, PR evidence).
5. Treat unknown/missing evidence as requirement gaps.

## 2. Modern UI Component Generation Constraints
When writing UI components for React/Vite environments:
- Use **Tailwind CSS** strictly for styling and layout. Do not write custom CSS or inline styles unless completely unavoidable.
- Prefer **Lucide React** for icons (`lucide-react`).
- Favor standard **shadcn/ui** or Radix-style functional layout patterns for base components (Cards, Dialogs, Inputs, Buttons) where feasible. Avoid heavy third-party UI framework vendor lock-in if standard Tailwind suffices.
- Prefer semantic HTML5 elements: `<nav>`, `<main>`, `<article>`, `<aside>`, `<section>`, `<header>`, `<footer>`.
- Default to **Flexbox** or **CSS Grid** for layout. Do not use floats or absolute positioning for standard document flow.

## 3. Interaction and State Management
- Ensure loading states include skeleton configurations or animated spinners.
- Ensure error states gracefully inform the user and provide a recovery action.
- Disable submit buttons during form mutations (`pending` states).
- Follow optimistic UI updating best practices where data mutations execute in the background.

## 4. Accessibility (A11y) Baseline
- Ensure all interactive elements have highly visible `focus-visible` state rings with Tailwind (e.g., `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`).
- Include `aria-label` or `sr-only` text tags for icon-only buttons.
- Manage focus trapping inside modals and dialogs safely.
- Meet WCAG AA contrast ratios minimum for text against backgrounds.

## Required Modules

Use and enforce:
- `.copilot/skills/ux-ia-navigation/SKILL.md`
- `.copilot/skills/ux-responsive/SKILL.md`
- `.copilot/skills/ux-artifact-grouping/SKILL.md`
- `.copilot/skills/ux-a11y-basics/SKILL.md`
- `.copilot/skills/ux-pr-checklist/SKILL.md`
- `.copilot/skills/ux-consult-request/SKILL.md`
- `.copilot/skills/ux-context-sources/SKILL.md`

## Output Contract

Return a strict decision header on first line:
- `UX_DECISION: PASS`
- `UX_DECISION: CHANGES`

If CHANGES, include a short ordered remediation list and blocking severity.

Required sections after decision header:
- `Navigation Plan:`
- `Responsive Rules:`
- `Tailwind & Components:`
- `Grouping Decisions:`
- `A11y Baseline:`
- `Requirement Check:`
- `Requirement Gaps:`
- `Risk Notes:`
- `Required Changes:` (if CHANGES)

## Instructions

- Follow domain guidelines.
</file>
</skill>
