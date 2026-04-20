<skill>
<name>prompt-quality-baseline</name>
<description>Workflow or rule module extracted from .copilot/skills/prompt-quality-baseline/SKILL.md</description>
<file>
# Prompt Quality Baseline

## Objective

## When to Use

- Use this when working on tasks related to prompt quality baseline.

## When Not to Use

- Do not use this when the current task does not involve prompt quality baseline.

## When to Use

- Use this when working on tasks related to prompt quality baseline.

## Objective

Provides context and instructions for the `prompt-quality-baseline` skill module.

## Required Sections

Each operational prompt (non-README) should include:

- Objective
- When to Use
- When Not to Use
- Inputs
- Constraints
- Output Format
- Completion Criteria

## Docs Grounding Guardrail (Context7)

- For external API/library/framework behavior, prompts must require Context7-backed documentation grounding.
- For internal architecture and implementation details, prompts must prioritize repository conventions and local codebase facts.
- If version-specific docs are ambiguous, prompts must require explicit assumptions in output.

## MCP Tool Arbitration Hard Rules

When more than one MCP server or generic execution path could complete a task, prompts must enforce this
precedence and usage model:

1. Prefer the most specialized domain MCP server over generic servers and terminal/shell execution.
2. Use `git` MCP for repository history/state operations (`status`, `diff`,
   `log`, `show`, `blame`, branch tasks).
3. Use `search` MCP for codebase content discovery and text matching before
   file reads.
4. Use `filesystem` MCP for deterministic file CRUD inside workspace scope;
   never use it for git-history questions.
5. Use `dockerCompose` MCP for container/compose lifecycle and health/log
   operations; do not route these through generic shell paths first.
6. Use `testRunner` MCP for lint/build/test execution profiles before any
   fallback.
7. Use `bashGateway` MCP only for allowlisted script workflows or when a
   required domain action has no dedicated MCP capability; it is not the
   default executor for arbitrary commands.
8. For external API/library docs, use Context7 when online; when offline, use
   `offlineDocs` MCP for indexed local docs; use `search` MCP only when
   `offlineDocs` does not cover required content.

9. For local docs Q&A on repository documentation, prefer `offlineDocs` MCP for
   index/search/read; use `filesystem` read only for exact-path excerpts.
10. Keep `offlineDocs` index lifecycle change-driven: refresh after `docs/` or
    `templates/` source changes; do not require boot-time rebuilds.
11. Treat generic terminal execution as a last-resort fallback only when no
    suitable MCP server or tool can satisfy the task. Broad terminal approval
    or auto-approve settings must not be treated as a reason to bypass MCP
    routing.

Prompts must treat these as hard rules, not preferences.

## Size Guidance

- `agents/*.md`: target <= 100 lines
- Non-agent prompts: keep concise; split if > 200 lines
- Exceptions must include a short justification in-file

## Anti-Patterns

- Monolithic prompts with duplicated instructions
- Missing output contract
- Vague completion criteria ("done when done")
- Cross-repo instructions without merge/deploy order

## Validation

- Run: `python scripts/check_prompt_quality.py`
- Run: `python scripts/check_context7_guardrails.py`
- Verify links: `rg -n "\]\(.*\)" .copilot/skills --glob '*.md'`

## Instructions

- Follow domain guidelines.
  </file>
  </skill>
