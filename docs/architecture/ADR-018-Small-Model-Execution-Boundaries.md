# ADR-018: Small-Model Execution Boundaries

## Status

Accepted

## Context

- As we leverage smaller, specialized models for issue resolution, they struggle to manage unbounded context windows, large file counts, or diffuse conceptual domains in a single operational slice.
- When execution slices grow too large, maintaining tight feedback loops (such as Local CI Parity from ADR-006) fails and architectural enforcement (ADR-013) becomes unreliable.
- To predictably succeed on smaller models, we need strict, bounded budgets for target files, diff sizes, and conceptual scope, as well as explicit steps for read-before-write, validation, and issue handoff.

## Decision

To ensure small-model execution reliability, all workflow steps and execution slices MUST adhere to the following bounded constraints:

### 1. File and Scope Limits (Target-file & Domain constraint)
- **Target-file Limit:** An execution packet must prefer 1–3 target files and NEVER exceed 5 target files. If a task requires editing more than 5 files, it MUST be split into multiple discrete issues.
- **Conceptual Domain:** Each issue must focus on exactly ONE conceptual domain (e.g., "architecture decision", "script update", or "documentation typo").
- **Diff Budget:** An issue should prefer a total implementation diff of 150–250 lines.

### 2. Required Context and Rules (Read-first & Authority-anchor constraint)
- **Read-first Requirements:** Before any implementation begins, the execution packet MUST explicitly list required context files (e.g., specific ADRs or source files). The agent MUST read these files first.
- **Authority-anchor Constraint:** The execution packet MUST explicitly map the work to the governing architectural authorities (e.g., existing ADRs) so the model anchors its approach correctly.

### 3. Safety and Validation Boundaries (Validation-first & Forbidden-behavior constraint)
- **Validation-first Rule:** The agent MUST run the narrowest applicable local validation step first (e.g., structural verification or `grep`) before proceeding to wider repository CI validations.
- **Forbidden Behavior:** Small-model slices MUST NOT perform:
  - Broad repository rewrites.
  - Software component release bumps.
  - Bypassing standard activation or workflow wrappers.
  - Raw `gh pr merge`, `git push`, or `gh issue close`.

### 4. Pipeline Continuation (Unlock-next-issue constraint)
- **Unlock-next-issue:** Each compact execution packet MUST declare whether it unlocks a subsequent downstream issue in the pipeline, communicating this state upon PR handoff.

## Downstream projections

- `.github/ISSUE_TEMPLATE/compact-execution-slice.md`
- `docs/architecture/ADR-006-Local-CI-Parity-Prechecks.md`
- `docs/architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md`
- `.github/copilot-instructions.md`

## Consequences

- We can predictably execute issue pipelines using faster, smaller models.
- Work planning becomes more rigorous and modular.
- Execution handoffs cleanly communicate blocker and downstream status.
