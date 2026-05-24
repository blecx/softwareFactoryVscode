---
name: prompt-quality-baseline
description: "Prompt quality baseline: enforces structural requirements, explicit contracts, and MCP tool precedence for operational prompts."
---

# Prompt Quality Baseline

## Objective
Enforces structural requirements, explicit contracts, and MCP tool precedence to ensure high-quality operational prompts and agent instructions.

## When to Use
- You are authoring, reviewing, or refactoring an AI prompt, agent file, or skill module.
- You are diagnosing why an agent is failing to adhere to expected structures or tool routing.

## When Not to Use
- You are writing purely human-facing documentation (like a standard README).
- You are generating application code rather than prompt or agent instructions.

## Required Sources
- `scripts/check_prompt_quality.py`
- `scripts/check_context7_guardrails.py`

## Constraints
- Anti-Patterns to avoid: Monolithic prompts with duplicated instructions, missing output contracts, vague completion criteria ("done when done"), and cross-repo instructions without merge/deploy order.
- Each operational prompt (non-README) should include: `Objective`, `When to Use`, `When Not to Use`, `Inputs`, `Constraints`, `Output Format`, and `Completion Criteria`.
- For external API/library/framework behavior, prompts must require Context7-backed documentation grounding.
- For internal architecture and implementation details, prompts must prioritize repository conventions and local codebase facts.
- If version-specific docs are ambiguous, prompts must require explicit assumptions in output.
- `agents/*.md`: target <= 100 lines.
- Non-agent prompts: keep concise; split if > 200 lines. Exceptions must include a short justification in-file.

MCP Tool Arbitration Hard Rules (When more than one MCP server or generic execution path could complete a task):
1. Prefer the most specialized domain MCP server over generic servers and terminal/shell execution.
2. Use `git` MCP for repository history/state operations (`status`, `diff`, `log`, `show`, `blame`, branch tasks).
3. Use `search` MCP for codebase content discovery and text matching before file reads.
4. Use `filesystem` MCP for deterministic file CRUD inside workspace scope; never use it for git-history questions.
5. Use `dockerCompose` MCP for container/compose lifecycle and health/log operations; do not route these through generic shell paths first.
6. Use `testRunner` MCP for lint/build/test execution profiles before any fallback.
7. Use `bashGateway` MCP only for allowlisted script workflows or when a required domain action has no dedicated MCP capability; it is not the default executor for arbitrary commands.
8. For external API/library docs, use Context7 when online; when offline, use `offlineDocs` MCP for indexed local docs; use `search` MCP only when `offlineDocs` does not cover required content.
9. For local docs Q&A on repository documentation, prefer `offlineDocs` MCP for index/search/read; use `filesystem` read only for exact-path excerpts.
10. Keep `offlineDocs` index lifecycle change-driven: refresh after `docs/` or `templates/` source changes; do not require boot-time rebuilds.
11. Treat generic terminal execution as a last-resort fallback only when no suitable MCP server or tool can satisfy the task. Broad terminal approval or auto-approve settings must not be treated as a reason to bypass MCP routing.
Prompts must treat these as hard rules, not preferences.

## Completion Contract
- Ensure proper validation:
  - Run: `python scripts/check_prompt_quality.py`
  - Run: `python scripts/check_context7_guardrails.py`
  - Verify links: `rg -n "\]\(.*\)" .copilot/skills --glob '*.md'`
- Ensure the prompt strictly conforms to the objective, explicit boundaries, constraints, and tool arbitration rules.
