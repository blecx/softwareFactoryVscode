# ADR-018: Workflow Preflight Evidence Schema and Consumer Matrix

## Status

Accepted

## Context

- **Architecture/Authority Gap**: Workflow entrypoints and AI agents currently lack a formalized schema and consumer matrix for preflight evidence. This allows inconsistencies where some workflows might bypass readiness or authority prechecks due to missing or improperly formatted evidence.
- **Constraining ADRs**: `ADR-013-Architecture-Authority-and-Plan-Separation` mandates that architecture terminology, consumer matrices, and authority guardrails be defined in an ADR. `ADR-006` and `ADR-016` establish the local CI parity prechecks and ubiquitous language policy that preflight evidence ultimately enforces.
- **Downstream Projections**: Workflows (issue, queue, PR merge, and interruption recovery) will project this evidence to require safe transitions.

## Decision

### 1. Authority / precedence

- **Rule**: `ADR-018` is the normative owner of the Workflow Preflight Evidence Schema (`schemas/workflow-preflight-evidence.schema.json`) and its consumer matrix.
- **Rule**: Downstream entrypoints, workflow skills, and runtime automation may read and generate evidence according to this schema but MUST NOT redefine the required fields or lifecycle semantics.

### 2. Canonical form / contract

- **Rule**: Preflight evidence MUST conform to `schemas/workflow-preflight-evidence.schema.json`. It MUST include `evidence_key`, `agent`, `status`, and `timestamp`.
- **Consumer Matrix**: The following workflows and entrypoints are defined as normative consumers of the schema, meaning they MUST enforce its presence and validity before execution:
  1. `resolve-issue-workflow`: Consumes evidence before beginning implementation.
  2. `pr-merge-workflow`: Consumes evidence (along with CI parity) before pushing merges.
  3. `approved-plan-execution-workflow` (Queue Backend): Evaluates and refreshes evidence across slice boundaries.
  4. `interruption-recovery-workflow`: Relies on exact-state fields to rebuild continuity safely.
- **Affected surface families**: ADRs, maintainer docs, canonical `.copilot/skills/*`, and GitHub prompts.

### 3. Runtime / discovery preservation

- **Rule**: Preserve existing preflight output patterns (e.g., `scripts/workflow_preflight_gate.py`) but rigidly align them to this schema.

## Downstream projections

- `schemas/workflow-preflight-evidence.schema.json`
- `scripts/workflow_preflight_gate.py`
- `.copilot/skills/resolve-issue-workflow/SKILL.md`
- `.copilot/skills/pr-merge-workflow/SKILL.md`
- `.copilot/skills/approved-plan-execution-workflow/SKILL.md`

## Consequences

- Workflow preflight checking is now strictly uniform across all P0 entrypoints.
- It becomes structurally impossible to trigger bounded orchestration (like queue runners or PR merges) without mathematically sound, schema-validated entry state.
- Break-glass overrides are explicitly supported but formally classified as `status: bypassed` with a required `bypass_reason`.
