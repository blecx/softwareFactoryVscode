# Harness Artifact Inventory

_Targeted for Phase 0 of the Harness Namespace Implementation Backlog._

This document provides a concrete inventory of the active install, update, and runtime artifacts generated or managed by the Software Factory harness. It classifies ownership and records the current supported disposition of each artifact after the namespace-first cutover.

## Artifact Inventory

### Harness Namespace Root

Current location: `.copilot/softwareFactoryVscode/`  
Ownership class: canonical harness asset / managed namespace  
Supported disposition: keep as the canonical installed harness path

### Copilot Skills

Current location: `.copilot/softwareFactoryVscode/.copilot/skills/`  
Ownership class: canonical harness asset  
Supported disposition: keep namespaced under the harness root

### GitHub Agents

Current location: `.copilot/softwareFactoryVscode/.github/agents/`  
Ownership class: canonical harness asset  
Supported disposition: keep inside the harness unless projected intentionally

### GitHub Templates

Current location: `.copilot/softwareFactoryVscode/.github/pull_request_template.md` and related files  
Ownership class: canonical harness asset  
Supported disposition: keep inside the harness unless a documented projection requires otherwise

### Factory Runtime/Scripts

Current location: `.copilot/softwareFactoryVscode/factory_runtime/`, `scripts/`  
Ownership class: canonical harness asset  
Supported disposition: keep namespaced under `.copilot/softwareFactoryVscode/`

### Compose Definitions

Current location: `.copilot/softwareFactoryVscode/compose/`  
Ownership class: canonical harness asset  
Supported disposition: keep namespaced under `.copilot/softwareFactoryVscode/`

### Runtime Environment

Current location: `.copilot/softwareFactoryVscode/.factory.env`  
Ownership class: local-only / ephemeral runtime state  
Supported disposition: keep namespaced and ignore via `.gitignore`

### Lock File

Current location: `.copilot/softwareFactoryVscode/lock.json`  
Ownership class: managed install metadata  
Supported disposition: keep as the canonical managed-path/install record

### Transient Data

Current location: `.copilot/softwareFactoryVscode/.tmp/`  
Ownership class: local-only / ephemeral runtime state  
Supported disposition: keep namespaced and ignore via `.gitignore`

### Workspace File

Current location: `software-factory.code-workspace` at host root  
Ownership class: host-owned integration surface (generated once)  
Supported disposition: keep as the canonical operator entrypoint

### Git Ignore Block

Current location: `.gitignore` at host root  
Ownership class: host-owned integration surface  
Supported disposition: keep with the namespace-first `# Factory Isolation` block

### Legacy Root Artifacts

Current locations: `.softwareFactoryVscode/`, `.tmp/softwareFactoryVscode/`, root `.factory.env`, root `.factory.lock.json`  
Ownership class: deprecated migration leftovers  
Supported disposition: delete on install/update and fail verification if still present

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
   **Answer:** The generated `software-factory.code-workspace` file remains the canonical operator entrypoint. Legacy root install artifacts do not remain required.

3. **Which runtime facts must remain operator-visible?**
   **Answer:** `.factory.env` remains namespaced within `.copilot/softwareFactoryVscode/.factory.env`, while runtime health and endpoint facts are surfaced through the generated workspace, verifier output, and runtime manifest.
