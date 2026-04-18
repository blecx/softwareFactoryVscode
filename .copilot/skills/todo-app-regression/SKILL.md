---
name: todo-app-regression
description: Canonical todo-app regression workflow for release protection. Use when validating the full todo-app regression, checking throwaway execution paths, verifying Definition of Done and quality metrics, or confirming a different supported GitHub model still satisfies the todo-app semantic contract.
---

# Todo-app regression workflow

## Objective

Provide one canonical, `.copilot`-owned definition for the release-grade todo-app regression workflow used by `softwareFactoryVscode`.

## Canonical ownership

- The canonical contract lives under `.copilot/skills/todo-app-regression/`.
- Runtime evidence is disposable and MUST NOT become the canonical definition.
- The regression MUST NOT introduce a new host-root ownership surface.

## Throwaway execution paths

- **Source checkout mode:** `.tmp/todo-regression-run/workspace`
- **Installed host mode:** `.copilot/softwareFactoryVscode/.tmp/todo-regression-run/workspace`
- All runtime reports, generated artifacts, and temporary evidence MUST stay inside the approved throwaway workspace.
- Never write regression artifacts outside the approved throwaway workspace roots.

## Minimum todo-app contract

The regression MUST validate that a candidate todo-app deliverable covers all of the following behaviors:

- create todo
- edit todo
- mark complete/incomplete
- delete todo
- empty-state behavior
- persistence across reload/restart

## Definition of done

The todo-app regression is considered done only when all of the following are true:

- canonical skill committed under `.copilot`
- approved throwaway paths enforced
- minimum todo-app contract evaluated
- semantic model compatibility checks pass
- report written only in throwaway workspace
- no unexpected filesystem changes outside throwaway workspace

## Quality metrics

The regression MUST check and report these metrics:

- skill contract coverage: 100%
- definition of done coverage: 100%
- semantic compatibility rate: 100%
- throwaway cleanliness: 100%
- repeat-run stability: 100%

## Model and provider compatibility checks

- The current repository supports GitHub Models via `provider=github`.
- Changing to a different supported GitHub model MUST still pass when the semantic rubric is satisfied.
- Do not rely on exact wording from model output.
- Validate a structured response or semantic checklist instead of exact strings.
- Treat unsupported providers as an intentional regression failure.

## Execution steps

1. Resolve whether the runner is operating from a source checkout or an installed host repository.
2. Create a fresh throwaway workspace under the approved ignored root.
3. Audit the canonical skill contract for required sections, minimum feature list, Definition of Done terms, and quality metrics.
4. Evaluate the model compatibility cases with the semantic rubric.
5. Synthesize the active-config compatibility case using the current configured GitHub provider/model.
6. Re-run the semantic evaluation to confirm repeat-run stability.
7. Write the regression report and supporting artifacts inside the throwaway workspace only.
8. Fail the run if anything outside the throwaway workspace changed unexpectedly.

## Reporting contract

- Write the JSON report to `workspace/reports/todo-app-regression-report.json`.
- Write supporting artifacts to `workspace/artifacts/`.
- Include mode, throwaway root, quality metrics, Definition of Done coverage, active model/provider details, semantic compatibility results, and unexpected-change findings.
