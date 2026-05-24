# AI surface template and checklist

Use this after the relevant accepted ADR text is explicit. Plans, wrappers, and maintainer indexes must not redefine architecture first.

## Choose the approved canonical form

- **Form A — authority markdown:** plain Markdown for accepted ADRs and human reference docs.
- **Form B — structured module:** YAML frontmatter + Markdown sections for `.github/prompts/*` and canonical `.copilot/skills/*`.
- **Form C — `chatagent` discovery wrapper:** thin Markdown + fenced `chatagent` block for primary `.github/agents/*` entrypoints that participate in VS Code custom-agent discovery.
- **Form D — thin discoverability card:** minimal frontmatter + short delegation body for alias or namespace wrappers.

## Structured module template

```md
---
name: <surface-name>
description: "<literal one-line description>"
---

# <Title>

## Objective
<one literal paragraph>

## When to Use
- <concrete trigger phrase>
- <concrete trigger phrase>

## When Not to Use
- <explicit boundary>
- <explicit boundary>

## Required Sources
- <path>

## Constraints
- <guardrail>

## Completion Contract
<what the surface must return, decide, or hand off>
```

## `chatagent` discovery wrapper template

````md
## Objective

Provides context for the `<agent-name>` AI Agent.

```chatagent
---
description: "<literal one-line description>"
---

You are the `<agent-name>` custom agent.

This file is a VS Code discovery wrapper. Keep the real workflow logic in `<canonical skill or runbook path>`.
```

## When to Use
- <concrete trigger phrase>

## When Not to Use
- <explicit boundary>

## Required Sources
- <path>

## Hard Rules
- <guardrail>

## Completion Contract
<what the wrapper must return or delegate>
````

## Thin discoverability card template

```md
---
description: "<literal one-line description>"
---

# <alias-name>

<one-sentence delegation target>

This is a thin discoverability wrapper.

User request:
$ARGUMENTS
```

## Anti-drift checklist

- Use exactly one `## Objective`, one `## When to Use`, and one `## When Not to Use`.
- Use concrete trigger phrases instead of tautological repeats of the surface name.
- Remove placeholder instruction text such as `Follow domain guidelines.`
- Do not introduce new architecture, precedence, or canonical-form claims until an accepted ADR changes first.
- Preserve required wrapper syntax (`chatagent` fences or other active discovery markers).
- Keep thin wrappers thin: delegate to the canonical skill, prompt, ADR, or runbook instead of restating full policy text.
- Link canonical owner paths explicitly for `.github/prompts/*`, `.copilot/skills/*`, and `.github/agents/*`.
- Treat duplicate headings and mixed metadata hybrids as drift to normalize, not new approved forms.
