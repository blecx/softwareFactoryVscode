---
name: blecs-ux-authority
description: "blecs UX authority: mandatory consultation for navigation, graphical design, responsive behavior, modern React/Vite/Tailwind UI patterns, and UX/a11y review."
---

# blecs UX Authority Skill

## Objective
Provides the canonical constraints for UI/UX and modern Web App Generation code, ensuring a standardized, accessible, and responsive user experience. 

## When to Use
- You are designing or modifying navigation and information architecture.
- You are adding or changing graphical layouts, responsive behaviors, or implementing modern UI patterns (e.g., React, Vite, Tailwind CSS, shadcn/ui).
- You are generating new UI components or executing accessibility (a11y) reviews.
- A PR review touches UX-sensitive paths.

## When Not to Use
- You are working exclusively on backend services, databases, or API routes.
- The task does not involve frontend UI, styling, or component layout.

## Required Consultation Scope
Any AI assistant or agent that plans, implements, reviews, or merges changes that affect UI/UX must consult this skill first.
Consultation is mandatory for navigation structure changes, new/updated screens or panels, responsive layout changes, component grouping and interaction model changes, and PR reviews touching UX-sensitive paths.

## Constraints
1. Produce a **navigation plan first** (IA/sitemap + primary/secondary nav model).
2. Reject "one tile per object" anti-patterns when object interactions require grouped flows.
3. Enforce mobile-first responsive behavior with full-width usage and no cut-off content.
4. Run an explicit requirement check (navigation, responsive, grouping, a11y, PR evidence).
5. Treat unknown/missing evidence as requirement gaps.
6. Use **Tailwind CSS** strictly for styling and layout. Do not write custom CSS or inline styles unless completely unavoidable.
7. Prefer **Lucide React** for icons (`lucide-react`).
8. Favor standard **shadcn/ui** or Radix-style functional layout patterns for base components (Cards, Dialogs, Inputs, Buttons) where feasible. Avoid heavy third-party UI framework vendor lock-in if standard Tailwind suffices.
9. Prefer semantic HTML5 elements: `<nav>`, `<main>`, `<article>`, `<aside>`, `<section>`, `<header>`, `<footer>`.
10. Default to **Flexbox** or **CSS Grid** for layout. Do not use floats or absolute positioning for standard document flow.
11. Ensure loading states include skeleton configurations or animated spinners.
12. Ensure error states gracefully inform the user and provide a recovery action.
13. Disable submit buttons during form mutations (`pending` states).
14. Follow optimistic UI updating best practices where data mutations execute in the background.
15. Ensure all interactive elements have highly visible `focus-visible` state rings with Tailwind (e.g., `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`).
16. Include `aria-label` or `sr-only` text tags for icon-only buttons.
17. Manage focus trapping inside modals and dialogs safely.
18. Meet WCAG AA contrast ratios minimum for text against backgrounds.

## Required Sources
- `.copilot/skills/ux-ia-navigation/SKILL.md`
- `.copilot/skills/ux-responsive/SKILL.md`
- `.copilot/skills/ux-artifact-grouping/SKILL.md`
- `.copilot/skills/ux-a11y-basics/SKILL.md`
- `.copilot/skills/ux-pr-checklist/SKILL.md`
- `.copilot/skills/ux-consult-request/SKILL.md`
- `.copilot/skills/ux-context-sources/SKILL.md`

## Completion Contract
Return a strict decision header on the first line:
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
