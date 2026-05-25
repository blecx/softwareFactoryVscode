# ADR-017: Host Project Ubiquitous Language Boundary

## Status

Accepted

## Context

- The Software Factory manages its own internal workflow language via ADR-016 and its projections. However, a host project using the Software Factory needs to define its own ubiquitous language so project terminology survives SDK / factory updates.
- If the factory and host project mix their domain languages in a single configuration file, automated SDK updates will overwrite or corrupt the host language.
- This is constrained by ADR-012 (Workspace Tooling Installation Boundary), ADR-013 (Architecture Authority and Plan Separation), and ADR-016 (Workflow Ubiquitous Language and Ambiguity Policy).
- We need a defined machine-readable surface for the host project's language that is explicitly exempt from factory-managed updates.

## Decision

### 1. Authority / precedence

- **Rule:** The host project owns its ubiquitous domain language. The Software Factory owns its internal workflow terminology.
- **Rule:** The factory update mechanism MUST NOT overwrite host project language definitions. Host-domain terms MUST NOT be authored into factory-managed language files (`configs/workflow_language.yml`).
- **Rule:** AI agents resolving issue tickets MUST adapt to the host project's rules without conflicting with the factory's internal rules.

### 2. Canonical form / contract

- **Rule:** `.copilot/project-language.yml` is the default host-owned machine-readable surface for host project ubiquitous language.
- **Affected surface families:** [ADRs | prompts | skills | workspace guardrails]

### 3. Runtime / discovery preservation

- **Rule:** Preserve any current discovery syntax (for example `chatagent` fences or other active wrapper markers) until this ADR explicitly replaces it.

## Downstream projections

- `.copilot/project-language.yml`

## Consequences

- Automated workspace factory tools (such as `scripts/workspace_surface_guard.py` update mechanisms) must respect `.copilot/project-language.yml` as off-limits.
- Host projects can safely define and store their ubiquitous domain terminology without fear of it being overwritten during SDK updates.
