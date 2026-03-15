<skill>
<name>resolve-issue-workflow</name>
<description>Workflow or rule module extracted from .copilot/skills/resolve-issue-workflow/SKILL.md</description>
<file>
# Resolve Issue Workflow

## Objective
Provides context and instructions for the `resolve-issue-workflow` skill module.

## When to Use
- A specific issue number is provided for implementation.
- The user asks to pick the next issue and execute one issue-to-PR slice.

## When Not to Use
- Do not use this when the current task is NOT focused on implementing an active issue and turning it into a PR.

## Instructions
1. Select issue (backend-first, lowest number) and confirm scope.
2. Write compact plan: goal, scope, AC, files, validation commands.
3. Apply UX delegation policy from `.copilot/skills/ux-delegation-policy/SKILL.md` and capture required consultation outcome.
4. Implement minimal code changes in a dedicated branch.
5. Run required validations for touched areas explicitly using the active venv environment (NEVER global python):
   - Backend: `./.venv/bin/python -m black apps/api/`, `./.venv/bin/python -m flake8 apps/api/`, `./.venv/bin/python -m pytest tests/`
   - Frontend: `cd ../maestro-client/client && npm run lint`, `npm run build`, tests if configured.
6. Commit with `Fixes #<issue>` and push.
7. Create PR via GitHub CLI using the generated `.tmp` markdown file:
   `gh pr create --body-file .tmp/pr-body-<issue-number>.md --title "Fixes #<issue>: <Title>"`
8. Address CI failures by root cause and re-validate.

## Required Planning Shape
- Goal
- Scope / non-goals
- Acceptance criteria
- Target files/modules
- Validation commands

Prefer tool-driven discovery over pasting large context into chat.

## Validation Baseline
- Include command outputs/evidence in PR body.

## Repo Rules
- Select backend/TUI/CLI issues before client/UX issues.
- Keep one issue per PR.
- Use `.tmp/`, never `/tmp`.
- Never touch `projectDocs/` or `configs/llm.json`.
- Apply the canonical UX delegation policy before finalizing UI/UX-impacting work.

## Guardrails
- Validate issue spec (strict sections + body-size limit) for roadmap specs.
- Keep scope to small CI-safe slices (single issue, minimal domains), no architecture regressions outside scope.
- Avoid unrelated refactors.
- Keep diffs reviewable and DDD-compliant.
- Follow `.copilot/skills/ux-delegation-policy/SKILL.md` as the canonical delegation rule source.

## Completion Contract
Return a concise result that states:
- implemented issue,
- validation status,
- PR or blocking condition,
- any follow-up split/dependency if scope exceeded the slice.
</file>
</skill>
