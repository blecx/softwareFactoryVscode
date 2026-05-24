# ADR-XXX: [Decision title]

## Status

Proposed

## Context

- What architecture, authority, or canonical-form gap exists?
- Which accepted ADRs already constrain this decision?
- Which downstream AI-facing surfaces will need projection updates after the ADR lands?

## Decision

### 1. Authority / precedence

- **Rule:** [state the authoritative owner]
- **Rule:** [state which downstream surfaces may project but not redefine the decision]

### 2. Canonical form / contract

- **Rule:** [state the approved file form, contract boundary, or discovery rule]
- **Affected surface families:** [ADRs | maintainer docs | prompts | skills | agent wrappers]

### 3. Runtime / discovery preservation

- **Rule:** Preserve any current discovery syntax (for example `chatagent` fences or other active wrapper markers) until this ADR explicitly replaces it.

## Downstream projections

- `[file path]`
- `[file path]`
- `[file path]`

## Consequences

- [what future normalization or enforcement work becomes possible]
- [what remains non-normative or deferred]
