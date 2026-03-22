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
3. Reject or reformat work that does not follow `.github/ISSUE_TEMPLATE/feature_request.yml` or `.github/ISSUE_TEMPLATE/bug_report.yml`.
4. Apply UX delegation policy from `.copilot/skills/ux-delegation-policy/SKILL.md` and capture required consultation outcome.
5. Read `.github/workflows/ci.yml` and treat its checks as the minimum local precheck contract for this slice.
6. Implement minimal code changes in a dedicated branch.
7. Run required validations explicitly using the repo venv (NEVER global python), including the local equivalents of `.github/workflows/ci.yml` before opening a PR:
   - `./.venv/bin/black --check factory_runtime/ scripts/ tests/`
   - `./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/`
   - `./.venv/bin/flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841`
   - `./.venv/bin/pytest tests/`
   - `./tests/run-integration-test.sh`
8. Commit with `Fixes #<issue>` and push.
9. Create PR via GitHub CLI using the generated `.tmp` markdown file and `.github/pull_request_template.md` structure:
   `gh pr create --body-file .tmp/pr-body-<issue-number>.md --title "Fixes #<issue>: <Title>"`
10. Run `./scripts/validate-pr-template.sh .tmp/pr-body-<issue-number>.md` before creating or updating the PR.
11. Address CI failures by root cause and re-validate.

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
- Treat `.github/pull_request_template.md` as mandatory output structure for PR bodies.
- Do not ask GitHub Actions to discover preventable failures locally first; run the local CI-equivalent prechecks before PR creation.

## Completion Contract

Return a concise result that states:

- implemented issue,
- validation status,
- PR or blocking condition,
- any follow-up split/dependency if scope exceeded the slice.
  </file>
  </skill>
