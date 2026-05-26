# ADR-018: Workflow Preflight Evidence Schema and Consumer Matrix

## Status

Accepted

## Context

- **What architecture, authority, or canonical-form gap exists?**
  Workflow components (work-issue, next-issue, step2 backend queue, prmerge normal flow, prmerge --force-bypass, approved-plan execution, interruption recovery) lack a canonical definition of what constitutes valid preflight evidence. Without this, evidence parsing is inconsistent and failure modes are ambiguous.
- **Which accepted ADRs already constrain this decision?**
  `ADR-013-Architecture-Authority-and-Plan-Separation.md` requires schemas to be defined by an accepted ADR rather than derived docs.
- **Which downstream AI-facing surfaces will need projection updates after the ADR lands?**
  Preflight evidence generators and validators.

## Decision

### 1. Authority / precedence

- **Rule:** The definition of the exact preflight evidence schema and its consumer matrix is authoritative here in this ADR.
- **Rule:** Derived docs and workflow implementations MAY project and validate against this schema but MUST NOT redefine the required schema fields or consumer matrix logic.

### 2. Canonical form / contract

- **Rule:** The schema must be versioned and must specify required fields: `identity`, `verdict`, and `timestamp`, as well as optional exact-state fields nested in an `exact_state` object containing fields such as `issue_number`, `pr_number`, `branch`, `worktree`, `request`, `request_hash`, `checkpoint`, `checkpoint_hash`, `github_truth_timestamp`, `expiration`, `break_glass`, `bypass_evidence`.
- **Consumer Matrix:**
  - `work-issue`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.issue_number`, `exact_state.branch`.
  - `next-issue`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.issue_number`.
  - `step2 backend queue`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.request` / `exact_state.request_hash`.
  - `prmerge normal flow`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.pr_number`, `exact_state.github_truth_timestamp`.
  - `prmerge --force-bypass break-glass`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.break_glass`, `exact_state.bypass_evidence`.
  - `approved-plan execution`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.request`, `exact_state.checkpoint`.
  - `interruption recovery`: Consumes `identity`, `verdict`, `timestamp`, `exact_state.worktree`, `exact_state.checkpoint`, `exact_state.expiration`.
- **Affected surface families:** ADRs, schemas

### 3. Runtime / discovery preservation

- **Rule:** Preserve any current discovery syntax (for example `chatagent` fences or other active wrapper markers) until this ADR explicitly replaces it.

## Downstream projections

- `schemas/workflow-preflight-evidence.schema.json`
- `scripts/workflow_preflight_gate.py`
- `tests/test_workflow_preflight_gate.py`

## Consequences

- We can implement a hard JSON schema validation step for all workflow transitions involving preflight checks.
- Workflow components must uniformly reject non-compliant evidence, standardizing our error diagnostics.