# AI Guardrails & Gatekeeper Guidelines

**Description:** Enforces strict adherence to project templates, GitHub process, and Markdown/JSON inter-agent protocols. ALWAYS apply these principles when working on tasks in this repository.

## 1. Gatekeeper: Reject Unformatted Input
- If a user asks you to implement a feature or fix a bug and does NOT provide an issue formatted according to the templates in `.github/ISSUE_TEMPLATE/` (e.g. `feature_request.yml` or `bug_report.yml`), **STOP**.
- Politely inform the user: "This Software Factory requires strict adherence to GitHub Issue templates to reduce AI drift. Please format your request using the issue templates before I can proceed."
- For PR summaries, strictly follow `.github/pull_request_template.md`. Do not invent new structures.

## 2. GitHub Process & GitOps Rules
- **NEVER** edit files directly on the `main` branch. 
- If you are on `main`, state that you must create a new branch named `issue-[id]` before beginning work.

## 3. A2A Communication (Markdown & JSON)
- Use standard `<thought_process>` XML tags around any abstract reasoning, brainstorming, or scratchpad notes. This scopes the output so downstream agents (extractors) can ignore the noise.
- When generating data for another agent or script to parse, use strict JSON schemas or standard Markdown primitive checklists (`- [ ]`).

## 4. Shift-Left CI
- Do not commit or pull request blindly. Always assume you must run the local equivalent of the CI validations.
- Run `tests/run-integration-test.sh` to ensure you haven't broken the isolated architecture.
- Run `scripts/validate-pr-template.sh` when generating PR descriptions.
