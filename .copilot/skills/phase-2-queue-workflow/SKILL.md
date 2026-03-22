<skill>
<name>phase-2-queue-workflow</name>
<description>Orchestrates the continuous loop for Phase 2 integration issues, delegating actual work to core workflows.</description>
<file>
# Phase 2 Queue Workflow

## Objective
Provides context and instructions for the `phase-2-queue-workflow` skill module.

## Role Contract

**phase-2 queue orchestration authority** - Manages the iterative issue-to-PR-merge loop specifically for Phase 2 integration tasks. Contains NO domain logic, implementation rules, or coding standards; entirely delegates work execution to canonical core workflows.

## Selection Scope

- Iteratively picks up Phase 2 integration tasks (for example, following the sequential backlog or issues labeled for Phase 2).

## Required Sources

- `.copilot/skills/a2a-communication/SKILL.md`
- `.copilot/skills/resolve-issue-workflow/SKILL.md`
- `.copilot/skills/pr-merge-workflow/SKILL.md`
- `.github/workflows/ci.yml`
- `.github/pull_request_template.md`
- `docs/architecture/ADR-001-AI-Workflow-Guardrails.md`
- `docs/architecture/ADR-005-Strong-Templating-Enforcement.md`
- `docs/architecture/ADR-006-Local-CI-Parity-Prechecks.md`

## Loop Bounds & Stop Conditions

- **Batch Size**: Processes exactly one issue at a time (One Issue = One PR = One Merge).
- **Manual Checkpoint**: Stops and requests manual operator approval before beginning the next issue in the loop.
- **Error Halt**: Stops immediately without advancing if there is a CI failure, workflow error, merge conflict, or blocked PR.
- **Completion**: Breaks the loop gracefully when no more Phase 2 issues remain.

## Delegation Boundaries

- **Implementation**: MUST defer entirely to `.copilot/skills/resolve-issue-workflow/SKILL.md` to do the actual coding, validation, and PR creation.
- **Merge**: MUST defer entirely to `.copilot/skills/pr-merge-workflow/SKILL.md` to handle the PR merge and workspace cleanup processes.
- **UX/Domain Rules**: DO NOT evaluate or enforce UX checks, small-slice rules, or domain constraints here. Trust that `resolve-issue-workflow` will pull `.copilot/skills/ux-delegation-policy/SKILL.md` and enforce rules on its own.

## Guardrails

- Only continue queue work that is backed by a template-compliant GitHub issue.
- Treat `.github/pull_request_template.md` and `./scripts/validate-pr-template.sh` as mandatory PR handoff gates, not optional documentation.
- Require local CI-equivalent validation from `.github/workflows/ci.yml` before handing a slice from `resolve-issue` to `pr-merge`.
- Stop immediately if template evidence or precheck evidence is missing from the current slice.

## Orchestration Reporting

Use this specific loop-reporting template before pausing for operator approval:

```markdown
### 🔄 Phase 2 Queue Status
- **Last Resolved Issue:** [#<number> - <title>]
- **Result:** [Merged | Blocked | Failed]
- **Next in Queue:** [#<number> - <title>]
- **Wait State:** ⏸️ Awaiting explicit operator approval to proceed to next issue.
```

## Instructions

- Follow domain guidelines.
</file>
</skill>