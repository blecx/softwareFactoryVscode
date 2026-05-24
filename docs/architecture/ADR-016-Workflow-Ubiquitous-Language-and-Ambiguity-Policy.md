# ADR-016: Workflow Ubiquitous Language and Ambiguity Policy

## Status

Proposed

## Context

- **What architecture, authority, or canonical-form gap exists?**
  Workflow systems and AI agents often use terms like "issue", "PR", "plan", "execution slice", and "umbrella" loosely. Without a strict ubiquitous language, agents guess meaning, resulting in ambiguous boundaries, lost tracking, and unpredictable actions.
- **Which accepted ADRs already constrain this decision?**
  [`ADR-013-Architecture-Authority-and-Plan-Separation.md`](ADR-013-Architecture-Authority-and-Plan-Separation.md) establishes that architecture authority resides in ADRs rather than derived docs.
- **Which downstream AI-facing surfaces will need projection updates after the ADR lands?**
  Prompts, skills, and agent wrappers dealing with workflow state will require updates to align their vocabulary.

## Decision

### 1. Authority / precedence

- **Rule:** The definitive meaning of architecturally significant workflow terms (e.g., umbrella issue, execution slice, plan) MUST be defined in accepted ADRs.
- **Rule:** Derived docs, prompts, and maintainer maps MAY project but MUST NOT redefine workflow architecture terms.

### 2. Canonical form / contract

- **Rule:** Workflow terminology must be bounded, and missing terms default to being unapproved for automation decisions rather than open to AI guessing.
- **Affected surface families:** ADRs, maintainer docs, prompts, skills, agent wrappers

### 3. Runtime / discovery preservation

- **Rule:** Preserve any current discovery syntax (for example `chatagent` fences or other active wrapper markers) until this ADR explicitly replaces it.

## Downstream projections

- `.copilot/skills/resolve-issue-workflow/SKILL.md`
- `.github/copilot-instructions.md`

## Consequences

- We can implement hard schema checks on workflow definitions rather than relying on loose natural language.
- Ambiguity is treated as a hard stop condition rather than a cue to guess.
