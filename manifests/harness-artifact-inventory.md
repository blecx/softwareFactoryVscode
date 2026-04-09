# Harness Artifact Inventory

_Targeted for Phase 0 of the Harness Namespace Implementation Backlog._

This document provides a concrete inventory of current install, update, and runtime artifacts generated or managed by the Software Factory harness. It classifies ownership and defines the future disposition of each artifact, acting as the baseline for the namespace migration.

## Artifact Inventory

| Artifact                    | Current Location                                               | Ownership Class                                 | Future Disposition                                                                    |
| :-------------------------- | :------------------------------------------------------------- | :---------------------------------------------- | :------------------------------------------------------------------------------------ |
| **Hidden Harness Root**     | `.softwareFactoryVscode/`                                      | Canonical harness asset (Transitional root)     | **Migrate** to `.copilot/softwareFactoryVscode/` and `.github/softwareFactoryVscode/` |
| **Copilot Skills**          | `.softwareFactoryVscode/.copilot/skills/`                      | Canonical harness asset                         | **Migrate** to `.copilot/softwareFactoryVscode/skills/`                               |
| **GitHub Agents**           | `.softwareFactoryVscode/.github/agents/`                       | Canonical harness asset                         | **Migrate** to `.github/softwareFactoryVscode/agents/`                                |
| **GitHub Templates**        | `.softwareFactoryVscode/.github/pull_request_template.md` etc. | Canonical harness asset                         | **Optionalize** or Migrate to `.github/`                                              |
| **Factory Runtime/Scripts** | `.softwareFactoryVscode/factory_runtime/`, `scripts/`          | Canonical harness asset                         | **Migrate** to `.copilot/softwareFactoryVscode/`                                      |
| **Compose Definitions**     | `.softwareFactoryVscode/compose/`                              | Canonical harness asset                         | **Migrate** to `.copilot/softwareFactoryVscode/compose/`                              |
| **Runtime Environment**     | `.factory.env` at host root                                    | Local-only / ephemeral runtime state            | **Replace/Migrate** (evaluate if it can be namespaced or absorbed into registry)      |
| **Lock File**               | `.softwareFactoryVscode/factory.lock.json`                     | Local-only / ephemeral runtime state            | **Replace** with managed-path record                                                  |
| **Transient Data**          | `.copilot/softwareFactoryVscode/.tmp/`                         | Local-only / ephemeral runtime state            | **Keep** (ensure `.gitignore` coverage)                                               |
| **Workspace File**          | `software-factory.code-workspace` at host root                 | Host-owned integration surface (Generated once) | **Optionalize**                                                                       |
| **Git Ignore Block**        | `.gitignore` at host root                                      | Host-owned integration surface                  | **Keep** (update paths for target namespace)                                          |

## Ownership Classes

- **Canonical harness asset:** Files that are part of the core harness and must be updated identically from upstream.
- **Managed installed namespace artifact:** Files that have been installed into the target `.copilot` or `.github` subtrees.
- **Host-owned integration surface:** Files that belong to the host repository, even if initially generated or modified by the harness.
- **Local-only / ephemeral runtime state:** Temporary files created during operation (e.g., sockets, tmp files, agent plans).
- **Root-level bridge artifact:** Root-visible pointers or symlinks required for VS Code/GitHub discovery.

## Unresolved Ownership Questions

None. All Phase 0 open questions have been explicitly answered.

1. **What should the managed-path record be called and where should it live?**
   **Answer:** It replaces `factory.lock.json` and moves into `.copilot/softwareFactoryVscode/lock.json`.

2. **Which current root-level files are still required in the target model?**
   **Answer:** Deep nesting is supported. GitHub agents will be nested directly under `.github/softwareFactoryVscode/agents/` without needing root-level bridge files in `.github/agents/`.

3. **Which runtime facts must remain operator-visible?**
   **Answer:** `.factory.env` does not need to remain visible at the host root. It will be hidden within the namespace at `.copilot/softwareFactoryVscode/.factory.env`.
