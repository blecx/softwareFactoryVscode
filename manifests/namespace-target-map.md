# Namespace Target Map

_Targeted for Phase 1 of the Harness Namespace Implementation Backlog._

This document specifies the exact target structure for the namespace-first harness projection model, moving away from root `.softwareFactoryVscode` directories.

## Target Subtree Layout: `.copilot/softwareFactoryVscode/`

The `.copilot` namespace is the **primary semantic home** for the AI workflow harness.

| Asset Type          | Target Location                                   | Description/Notes                                            |
| :------------------ | :------------------------------------------------ | :----------------------------------------------------------- |
| **Copilot Skills**  | `.copilot/softwareFactoryVscode/skills/`          | Migration of `.copilot/skills/` from the canonical source.   |
| **Copilot Agents**  | `.copilot/softwareFactoryVscode/agents/`          | Migration of any Copilot-specific agents or instructions.    |
| **Factory Runtime** | `.copilot/softwareFactoryVscode/factory_runtime/` | Core python runtime for the harness MCP servers and scripts. |
| **Docker Compose**  | `.copilot/softwareFactoryVscode/compose/`         | Container definitions for the factory architecture.          |
| **Scripts**         | `.copilot/softwareFactoryVscode/scripts/`         | Install, runtime bootstrap, and verification scripts.        |
| **Data/Templates**  | `.copilot/softwareFactoryVscode/templates/`       | Configs and host templates required for bootstrapping.       |

## Target Subtree Layout: `.github/softwareFactoryVscode/`

The `.github` namespace is a **secondary integration surface**, used only where GitHub-specific discovery or CI workflow integration demands it.

| Asset Type                | Target Location                            | Description/Notes                       |
| :------------------------ | :----------------------------------------- | :-------------------------------------- |
| **GitHub Copilot Agents** | `.github/softwareFactoryVscode/agents/`    | Copilot GitHub workflow agents mapping. |
| **GitHub Workflows**      | `.github/softwareFactoryVscode/workflows/` | Potential CI mappings.                  |

## Bridge Files

Bridge files are root-visible artifacts necessary for host tool discovery that point back into the namespaced subtrees.

| Bridge File            | Required? | Justification                                                                                          |
| :--------------------- | :-------- | :----------------------------------------------------------------------------------------------------- |
| `.github/agents/*.md`  | **No**    | Deep nesting is supported. GitHub agents will exist only in `.github/softwareFactoryVscode/agents/`.   |
| `.copilot/skills/*.md` | **No**    | Deep nesting is supported. Copilot skills will exist only in `.copilot/softwareFactoryVscode/skills/`. |
| `.factory.env`         | **No**    | `.factory.env` is namespaced as `.copilot/softwareFactoryVscode/.factory.env`.                         |

## Host-Owned Namepaces (Never Projected)

The following assets must remain exclusively governed by the host. The harness may provide templates but will _not_ automatically project files into them:

- Root `.gitignore` (we will append to it safely, but never replace)
- Root `workspace.code-workspace`
- Root source code

## Open Questions explicitly asked (Phase 1 closure)

All Phase 1 open questions are resolved:

1. **Discovery of `.copilot/skills/`:** Deep nesting is supported, so no bridge files are required at `.copilot/skills/`.
2. **Discovery of GitHub Agents:** Deep nesting is supported, so GitHub Copilot agents live at `.github/softwareFactoryVscode/agents/`.
3. **Managed Path Record:** Replaces `factory.lock.json` and moves to `.copilot/softwareFactoryVscode/lock.json`.
