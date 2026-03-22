# ADR-005: Strong Templating Enforcement

## Status

Accepted

## Context

The Software Factory depends on structured GitHub Issues and Pull Requests to keep AI-assisted implementation aligned with repository intent. When templates are treated as optional, agents drift: scope becomes ambiguous, acceptance criteria weaken, validation evidence is omitted, and later workflow stages must guess what earlier stages meant.

`ADR-001` already established that template compliance is mandatory in principle. However, practical workflow changes can still dilute that rule if template enforcement is not treated as a first-class architectural boundary.

We need a stronger, explicit decision that templates are part of the runtime contract of the Copilot-native issue → branch → PR → merge workflow.

## Decision

We mandate **strong templating enforcement** across issue creation, issue resolution, queue orchestration, and PR merge workflows.

### 1. Templates Are Operational Contracts

- **Rule:** `.github/ISSUE_TEMPLATE/feature_request.yml` and `.github/ISSUE_TEMPLATE/bug_report.yml` are authoritative input contracts for implementation work.
- **Rule:** `.github/pull_request_template.md` is the authoritative output contract for Pull Request descriptions.
- **Rule:** Workflow docs and Copilot skills MUST reference these templates directly rather than paraphrasing them as optional guidance.

### 2. Agents Must Reject Untemplated Work

- **Rule:** If a feature or bug request does not conform to an approved issue template, the workflow MUST stop and request template-compliant input before implementation proceeds.
- **Rule:** If a PR body does not conform to `.github/pull_request_template.md`, the PR MUST be treated as incomplete and MUST NOT advance to merge.

### 3. Queue Orchestration Must Preserve Template Discipline

- **Rule:** Queue-oriented agents such as `queue-backend` and `queue-phase-2` MUST carry template requirements forward and MUST NOT silently downgrade them during loop orchestration.
- **Rule:** Any future workflow rename or refactor MUST preserve template references in both documentation and Copilot skill sources.

### 4. Template Compliance Must Be Testable

- **Rule:** Repository regression tests SHOULD assert that workflow docs and Copilot skills still reference the approved issue and PR templates.
- **Rule:** CI and local validation SHOULD continue to include template conformance checks where applicable.

## Consequences

- Templates become enforceable architecture, not just etiquette.
- Future workflow cleanups must preserve template references and rejection behavior explicitly.
- Drift caused by vague or incomplete issue/PR structure becomes easier to detect in review and regression tests.
