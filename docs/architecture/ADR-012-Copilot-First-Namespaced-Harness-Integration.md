# ADR-012: Copilot-First Namespaced Harness Integration

## Status

Accepted

## Context

`softwareFactoryVscode` has been discussed using two different mental models:

1. as a strictly isolated hidden-tree runtime attached to a host repository, and
2. as a reusable AI harness / SDK that intentionally enhances Copilot behavior across many repositories.

The second model reflects the intended product shape more accurately.

The project exists in its own repository so that improvements, bug fixes, prompts, agent behaviors, and workflow integrations can be maintained centrally and then rolled out across multiple host repositories. In that operating model, some installed artifacts are expected to live with the host repository and be cloned with it.

However, we must still avoid drift and accidental ownership confusion:

- host product source must remain distinct from harness artifacts,
- host repository tooling must not be silently overwritten,
- Copilot should remain robust when reasoning about the host project, and
- future VS Code / GitHub changes should not be blocked by factory-specific file takeover.

The original hidden-tree model attempted to solve this through a dedicated top-level `.softwareFactoryVscode/` directory. While that approach isolates the harness physically, it is not the preferred long-term integration model because it adds a custom root-level namespace that can feel foreign to host repositories and is not the most semantically natural place for AI workflow artifacts.

The intended direction is to prefer existing tooling namespaces that already carry the meaning "AI / workflow / repository tooling" rather than "product source code".

The concrete artifact, install, and update implications of this decision are specified in `docs/HARNESS-INTEGRATION-SPEC.md`.

## Decision

We adopt a **Copilot-first namespaced harness integration model**.

### 1. `softwareFactoryVscode` Is a Reusable AI Harness, Not Just a Hidden Runtime

- **Rule:** `softwareFactoryVscode` is a reusable, centrally maintained AI harness / SDK for host repositories.
- **Rule:** Its purpose is to enhance Copilot and related repository workflows across multiple projects, not merely to attach an opaque runtime beside them.

### 2. `.copilot` Is the Primary Semantic Home

- **Rule:** AI behavior, prompt assets, skills, instructions, agent metadata, and related Copilot-facing artifacts should prefer `.copilot` as their primary semantic home.
- **Rule:** When installed into a host repository, the preferred long-term location for factory-managed AI harness assets is a namespaced subtree under `.copilot/`, such as `.copilot/softwareFactoryVscode/`.
- **Reason:** `.copilot` already signals AI tooling rather than host product source, making it the most semantically robust integration surface.

### 3. `.github` Is a Secondary Integration Surface

- **Rule:** GitHub-specific workflow artifacts may be installed under a namespaced subtree in `.github/`, such as `.github/softwareFactoryVscode/`, when GitHub-facing discovery or workflow integration requires it.
- **Rule:** `.github` should be treated as an integration surface, not the primary semantic home of the harness.

### 4. Namespace Before Projection

- **Rule:** Factory-managed artifacts should remain namespaced before they are projected, mirrored, linked, or surfaced into any host-visible integration point.
- **Rule:** Host-root `.copilot`, `.github`, `.vscode`, and `.gitignore` locations must not become the canonical authoring source for factory internals.
- **Rule:** If thin bridge files or generated entrypoints are needed for tool discovery, they must remain minimal, explicit, and documented.

### 5. Host-Owned Tooling Remains Host-Owned

- **Rule:** Even when the factory integrates with `.copilot`, `.github`, `.vscode`, or `.gitignore`, those host namespaces remain host-owned.
- **Rule:** Update workflows must prioritize upstream integrity for managed assets but never destroy host state permanently. For `.copilot/softwareFactoryVscode/` updates, conflicts are handled by aggressively resetting to `origin/<ref>`, but only *after* taking an automated `git switch -c local-backup-*` branch backup of any dirty modifications.
- **Rule:** Active `.tmp` resources and running Docker workloads must be gracefully spun down (`factory_stack.py stop`) before updates proceed, preventing filesystem exhaustion or volume corruption.
- **Rule:** Overwrites to `software-factory.code-workspace` are applied atomically in-place, and `.factory.env` merges upstream schema additions while retaining user-injected secrets.

### 6. Copilot Must Preserve Host Project Task Focus

- **Rule:** The harness should use namespaces that help distinguish AI/workflow artifacts from host product source.
- **Rule:** For normal implementation tasks, Copilot workflows must continue to default to the host project's product context, treating harness artifacts as tooling/instruction context unless explicitly targeted.
- **Rule:** Workspace layout, documentation, and install/update behavior should reinforce this distinction.

### 7. The Hidden-Tree Model Becomes Legacy, Not the End State

- **Rule:** The current hidden-tree `.softwareFactoryVscode/` installation model is a valid implementation step but is not the preferred long-term integration shape.
- **Rule:** Future install/update work should move toward namespaced integration under `.copilot` first and `.github` second.
- **Rule:** Migration work must be planned explicitly and should preserve updateability from the central `softwareFactoryVscode` repository.

## Consequences

- The project gains a clearer product identity: a reusable Copilot-first harness rather than a custom root-level add-on tree.
- Future install/update changes can be evaluated against a stable namespace policy.
- `.copilot` becomes the primary architectural anchor for AI behavior, with `.github` used where GitHub-specific integration is required.
- Drift toward unmanaged root-level sprawl or silent host tooling takeover becomes easier to identify in review.
- The current hidden-tree installer and documentation should be treated as transitional where they conflict with this target model.
