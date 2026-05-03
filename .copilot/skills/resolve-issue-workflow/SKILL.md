<skill>
<name>resolve-issue-workflow</name>
<description>Workflow or rule module extracted from .copilot/skills/resolve-issue-workflow/SKILL.md</description>
<file>
# Resolve Issue Workflow

## Objective

Provides context and instructions for the `resolve-issue-workflow` skill module.

This is the canonical implementation and PR-preparation half of the repository's
issue → PR → merge process.

## When to Use

- A specific issue number is provided for implementation.
- The user asks to pick the next issue and execute one issue-to-PR slice.
- A PR or branch failed CI and needs implementation fixes before returning to
  merge readiness.

## When Not to Use

- Do not use this when the current task is NOT focused on implementing an active issue and turning it into a PR.

## Instructions

1. Select issue (backend-first, lowest number) and confirm scope.
2. Write compact plan: goal, scope, AC, files, validation commands.
3. Reject or reformat work that does not follow `.github/ISSUE_TEMPLATE/feature_request.yml` or `.github/ISSUE_TEMPLATE/bug_report.yml`.
4. Apply UX delegation policy from `.copilot/skills/ux-delegation-policy/SKILL.md` and capture required consultation outcome.
5. Read `.github/workflows/ci.yml` and treat its checks as the minimum local precheck contract for this slice.
   - Prefer `./scripts/noninteractive_gh.py` or another pager-free `gh ... --json ...` pattern for GitHub polling in automation-heavy loops, and never combine piped JSON with a heredoc-based Python command because the heredoc consumes stdin.
   - For PR handoff/readiness narration, the canonical local shared-engine evidence command is `./.venv/bin/python ./scripts/local_ci_parity.py --level merge`.

### Ground symbols before editing code

- Verify the target definition and at least one repo-backed usage/reference before changing an existing contract, or verify from the issue text plus repo evidence that a genuinely new contract is required.
- Do **not** invent members, attributes, parameters, return fields, config keys, helper APIs, or data-shape fields that are not evidenced by the repository or the issue.
- Treat missing attribute/function errors, unresolved symbol assumptions, and guessed helper calls as grounding failures: stop, gather evidence from definitions/usages, and only then continue implementation or repair.
6. Implement minimal code changes in a dedicated branch.
   - When the slice is part of queue or approved-plan execution, work only from the issue's dedicated registered worktree and keep that worktree isolated from the dirty primary checkout and every other issue branch.
   - When a workflow task depends on `Host Project (Root)` or the installed-workspace contract, route it through the generated `software-factory.code-workspace` surface or the repo-owned `scripts/workspace_surface_guard.py` helper. Do not treat the source checkout as a second static runtime contract.
7. Run required validations explicitly using the repo venv (NEVER global python), including the local equivalents of `.github/workflows/ci.yml` before opening a PR:
   - `./.venv/bin/black --check factory_runtime/ scripts/ tests/`
   - `./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/`
   - `./.venv/bin/flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841`
   - `./.venv/bin/pytest tests/`
   - `./tests/run-integration-test.sh`
   - Maintain `.tmp/github-issue-queue-state.md` throughout the slice and record the latest validation command/result there.
   - When the shared checkpoint is active, keep `active_worktree` current alongside `active_issue` and `active_branch` so the slice can be resumed from the exact issue-specific execution surface.
8. Commit with `Fixes #<issue>` and push.
   - Before handing off to merge, update `.tmp/github-issue-queue-state.md` with `status: ready-for-pr-merge` plus `issue_state`, `pr_state`, `ci_state`, `cleanup_state`, and `last_github_truth`; that checkpoint is consumed by `pr-merge`, approved-plan execution, and interruption recovery.
   - `last_github_truth` must record the exact helper command(s), selector(s), and current result summary used for the readiness claim, for example `./.venv/bin/python ./scripts/noninteractive_gh.py issue-view <issue>` and `./.venv/bin/python ./scripts/noninteractive_gh.py pr-view <pr>` / `pr-checks <pr>`.
9. Create PR via GitHub CLI using the generated `.tmp` markdown file and `.github/pull_request_template.md` structure:
   `gh pr create --body-file .tmp/pr-body-<issue-number>.md --title "Fixes #<issue>: <Title>"`
10. Run `./scripts/validate-pr-template.sh .tmp/pr-body-<issue-number>.md` before creating or updating the PR.
11. Address CI failures by root cause and re-validate.

- Default to the repository's fast evidence-first repair tactic from `.github/prompts/pr-error-resolve-tactic.prompt.md`, even when that prompt was not explicitly invoked.
- Parse the exact current failure output before rerunning anything. If the output names a file, test, assertion, method, or check step, read that exact source before broader search or validation.
- Use the **formatter-first** strategy as the default narrow repair path: reproduce the cheapest failing gate first. When Python formatting drift is plausible, run Black and isort on touched Python files before broader tests or parity. Ladder: touched-file formatter check → single failing test/file → touched-test bundle → focused local parity → broader PR/merge validation. Widen validation only after the narrower gate passes.
- Before changing code after a failed PR-body/template check, local validation, or GitHub CI/check, quote the exact failing command/check, the relevant error text, and the suspected root cause from the latest evidence.
- Do **not** start with broad repo scans, full parity reruns, guessed fixes, hallucinated state, or stale-memory narration when a narrower deterministic gate already exists.
- Do **not** make a second repair change without new evidence; trial-and-error churn is non-compliant with the canonical issue → PR → merge flow.
- If repair work hits a missing attribute/function, unresolved symbol, or mismatched contract, treat it as a grounding failure first: confirm the real definition/usages before changing signatures, fields, or helper calls.

- If merge work discovers failing CI or merge-readiness issues that require code changes, stay on the same issue/branch and continue using this workflow rather than inventing a separate PR-repair path.

## Required Planning Shape

- Goal
- Scope / non-goals
- Acceptance criteria
- Target files/modules
- Validation commands

Prefer tool-driven discovery over pasting large context into chat.

## Validation Baseline

- Include command outputs/evidence in PR body.
- For PR handoff/readiness evidence, include `./.venv/bin/python ./scripts/local_ci_parity.py --level merge` plus the exact `./.venv/bin/python ./scripts/noninteractive_gh.py ...` GitHub-truth commands that support the current checkpoint state.

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
- Ground symbol and contract changes in repo evidence before editing.
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
