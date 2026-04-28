# Harness Integration Specification

This document translates the architectural direction from `ADR-012` into a concrete specification for artifacts, installation behavior, update behavior, and ownership boundaries.

It is intentionally more specific than the explainer in `docs/COPILOT-HARNESS-MODEL.md`, but still focused on product-level rules rather than implementation details.

See also:

- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/COPILOT-HARNESS-MODEL.md`
- `docs/archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- `docs/INSTALL.md`

## Purpose

This specification exists to prevent drift in four areas:

1. what artifacts the harness is allowed to create,
2. where those artifacts should live,
3. how install/update workflows should behave, and
4. how to keep the architecture understandable to both humans and Copilot.

## Canonical source vs installed projection

`softwareFactoryVscode` remains the **canonical source repository** for the harness.

Host repositories receive a **managed installed projection** of that harness.

This means:

- authoring happens in the `softwareFactoryVscode` repository,
- install/update workflows synchronize approved artifacts into host repositories,
- and host repositories should not become the accidental canonical source for harness internals.

## Artifact classes

All harness-related artifacts should be classified using the following model.

### 1. Canonical harness assets

These are defined and maintained in the `softwareFactoryVscode` repository.

Examples include:

- Copilot prompts and instructions
- Copilot skills
- agent metadata
- harness documentation
- MCP integration metadata
- GitHub-facing workflow support files

These assets are the source of truth for future install/update behavior.

### 2. Managed installed namespaces

These are the preferred long-term target locations inside host repositories.

#### Primary managed namespace

- `.copilot/softwareFactoryVscode/`

This namespace should hold the primary Copilot-facing harness assets, including, where appropriate:

- prompt and instruction files
- skill definitions
- AI workflow policy documents
- harness-local configuration
- namespaced documentation or manifests needed by the harness

#### Secondary managed namespace

- `.github/softwareFactoryVscode/`

This namespace should hold GitHub-specific harness assets only when GitHub-facing integration requires them, such as:

- agent definitions that must be discoverable through `.github`
- workflow-support files that are semantically GitHub-facing
- templates or fragments that are part of the harness rather than the host project's own native process

### 3. Host-owned integration surfaces

These remain host-owned even when the harness installs managed content nearby:

- `.copilot/`
- `.github/`
- `.vscode/`
- `.gitignore`
- host product source trees and tests

The harness may integrate with these areas, but must not silently claim ownership of them.

### 4. Local-only / ephemeral runtime state

These are operational artifacts and should remain optional, minimal, and preferably local-only wherever practical.

Examples include:

- secrets
- service health state
- temporary manifests
- transient runtime caches
- port allocation state
- machine-local runtime bookkeeping

The presence of these artifacts should not define the long-term product identity of the harness.

### 5. Root-level bridge artifacts

Root-level bridge artifacts are allowed only when required for tool discovery or operator ergonomics.

Examples may include:

- a generated workspace entrypoint
- a thin compatibility file required by a host tool
- a small manifest identifying managed harness paths

Rules:

- they must remain minimal,
- they must be clearly documented,
- and they must not become the canonical storage location for harness internals.

## Target artifact direction

The preferred long-term direction is:

- primary harness assets under `.copilot/softwareFactoryVscode/`
- GitHub-facing integration assets under `.github/softwareFactoryVscode/`
- minimal root-level bridge files only where needed

## Installation contract

The long-term installation contract should follow these rules.

### Install must

- install factory-managed artifacts into the managed namespaced subtrees,
- create only the minimal required bridge artifacts outside those subtrees,
- record what paths are factory-managed,
- and clearly distinguish managed artifacts from host-owned artifacts.

### Install must not

- silently overwrite host customizations in host-owned namespaces,
- treat transient runtime scratch state as the core success criterion of installation,
- or require a custom root-level namespace when an existing tooling namespace is sufficient.

### Managed-path record

The install/update system should maintain a small machine-readable record of:

- the installed harness version or source revision,
- which host paths are managed by the harness,
- and which files are generated bridge artifacts rather than canonical harness content.

This record is part of the future target contract because it makes safe updates possible.

## Update contract

The long-term update contract should follow these rules.

### Update may

- refresh factory-managed artifacts in managed namespaces,
- refresh generated bridge files that are explicitly factory-managed,
- and migrate managed assets between approved namespaces when the migration is documented and intentional.

### Update must not

- overwrite host-owned files just because they live in `.copilot`, `.github`, or `.vscode`,
- erase host customizations without an explicit conflict strategy,
- or depend on ambiguous ownership assumptions.

### Conflict strategy

If an update encounters a file in a host-owned integration surface, the update workflow must know one of the following:

1. the file is factory-managed and safe to update,
2. the file is host-owned and must be preserved,
3. the file is generated and may be regenerated,
4. or the file is in conflict and requires explicit operator action.

If the system cannot determine which case applies, it must treat the file as non-safe to overwrite.

## Consistency rules

To keep the architecture clear over time:

1. docs must distinguish **current implementation** from **target architecture** when they differ,
2. ADRs define the direction; this document defines the artifact and lifecycle contract,
3. install/update code should use the same ownership vocabulary as these docs,
4. regression tests should assert the managed namespace model,
5. and future maintainers should not have to infer ownership from installer side effects alone.

## What this means for implementation and follow-up

This specification defines the current artifact and lifecycle contract for the namespace-first harness model.

The mitigation and backlog documents record the migration rationale, the staged implementation sequence, and the remaining follow-up work needed to close gaps such as the fuller managed-path record and the broader ownership-aware update model.

See:

- `docs/archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- `docs/archive/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`
