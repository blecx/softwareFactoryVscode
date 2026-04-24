# Software Factory for VS Code

Welcome to the **Software Factory for VS Code**, a local, AI-powered development environment that seamlessly integrates autonomous agents and advanced Model Context Protocol (MCP) tooling directly into your VS Code workspace.

## Current Release

- **Latest release:** `2.5`
- **Release notes for GitHub:** [`.github/releases/v2.5.md`](.github/releases/v2.5.md)
- **Machine-readable release metadata:** [`manifests/release-manifest.json`](manifests/release-manifest.json)
- **Full changelog:** [`CHANGELOG.md`](CHANGELOG.md)

## What is this project?

This project provides a pre-configured, multi-tenant capable AI agent runtime designed to automate many aspects of the software development lifecycle. By running a local mesh of dockerized MCP servers (spanning memory, GitHub operations, devops, bash gateways, and repository fundamentals), the Software Factory creates a secure and highly capable back-end for your local AI coding assistants.

It transforms a standard repository into an intelligent "Factory" where you can collaborate with AI agents to build, test, and merge code using standardized, repeatable workflows.

## How it integrates in VS Code

The Software Factory is deeply integrated into VS Code to provide a frictionless developer experience:

- **VS Code Tasks:** Built-in tasks (like `🐳 Docker: Build & Start`, `💼 Select Next PR`, or `🚀 Start: Full Stack (Dev)`) power the complete workflow directly from the Command Palette or Terminal menu.
- **Runtime Lifecycle Management:** Use the provided runtime tasks to start and stop the companion Software Factory stack when needed. The source checkout no longer pins a separate static MCP URL contract into `.vscode/settings.json`.
- **Native MCP Client:** It exposes standard Model Context Protocol servers to your VS Code AI extensions (like GitHub Copilot), enriching the AI's context with specific repository knowledge, execution capabilities, and isolated memory stores.
- **Interactive Chat Agents:** Work via the Copilot Chat interface using one canonical issue-to-merge slice process: `@resolve-issue` for implementation, `@pr-merge` for PR validation/merge, `@execute-approved-plan` for bounded multi-issue execution, and `@queue-backend` / `@queue-phase-2` as scoped manual-checkpoint wrappers over that same process.

## Why it improves the development experience

- **Context-Aware AI:** The MCP servers provide your AI assistant with deep, precise knowledge about your specific codebase, deployment patterns, and operational standards.
- **Safe Execution:** The `approval-gate` and restricted `mcp-bash-gateway` securely sandbox AI actions, ensuring that autonomous code modifications or command executions stay within defined safety constraints.
- **Reduced Context Switching:** You can triage issues, read documentation, run smoke tests, and merge PRs within a single, unified IDE experience without constantly tabbing out to GitHub or other external tools.
- **Standardized Workflows:** Through automated workflows, every developer gets the same baseline guardrails and testing tools, significantly increasing code quality and velocity.

## Getting Started

### Prerequisites

To use the Software Factory, you need the following:

- **Visual Studio Code**. For the default AI experience documented here, VS Code `1.116+` is recommended because GitHub Copilot is built in as of that release.
- A **GitHub account with GitHub Copilot access** (paid plan or Copilot Free) if you want chat, inline suggestions, or agents enabled.
- _(Optional)_ The **GitHub Pull Requests and Issues** extension if you want GitHub PR/issue UI inside VS Code. It is not required for Copilot chat, inline suggestions, or agents.

**Configuring Copilot for the Factory:**

1. **VS Code `1.116+`** — GitHub Copilot is built in. Open the Copilot status item, choose `Use AI Features`, and sign in.
2. **Older VS Code releases** — install the [GitHub Copilot extension](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) first, then sign in.
3. Sign in with a GitHub account that has Copilot access. If you do not already have a paid plan, eligible users can be enrolled in **Copilot Free** during setup.
4. _(Optional for custom endpoint/model setups)_ If your environment layers a custom endpoint on top of Copilot, configure `github.copilot.advanced` in `settings.json` or use a compatible proxy setup after sign-in.
5. _(Optional)_ Install the [GitHub Pull Requests and Issues extension](https://marketplace.visualstudio.com/items?itemName=GitHub.vscode-pull-request-github) only if you want GitHub PR/issue UI inside VS Code. It is separate from Copilot and not required for the Factory's core AI workflows.

For the official editor-side guidance behind this version split, see the [VS Code 1.116 release notes](https://code.visualstudio.com/updates/v1_116) and the [Copilot setup guide](https://code.visualstudio.com/docs/copilot/setup).

### Installation

To install and initialize the Software Factory in your target repository, please follow the detailed step-by-step instructions in the installation guide.

➡️ [Read the Installation Guide](docs/INSTALL.md)

### Keeping an install current

Every namespace-first install now includes a built-in updater surface:

- `python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check`
- `python3 .copilot/softwareFactoryVscode/scripts/factory_update.py apply`

The updater reads the installed `lock.json`, compares it against the structured
release manifest published in `manifests/release-manifest.json`, and then uses
the canonical installer/update flow to apply a safe refresh when needed.

### Usage & Documentation

Once installed, check out our user guides to learn how to operate the factory effectively:

- **[User Handout](docs/HANDOUT.md):** A detailed overview of concepts and workflows.
- **[Cheat Sheet](docs/CHEAT_SHEET.md):** Quick reference for common tasks and CLI commands.
- **[Issue Workflow](docs/WORK-ISSUE-WORKFLOW.md):** Learn how to work through issues using Copilot agents.
- **[Internal Production Readiness Contract](docs/PRODUCTION-READINESS.md):** Canonical scope, blocking requirements, and sign-off rules for internal self-hosted production.
- **[Internal Production Readiness Plan](docs/PRODUCTION-READINESS-PLAN.md):** Issue-ready hardening plan for internal self-hosted production, explicitly excluding external hosted multi-tenant SaaS scope.
- **[Copilot Harness Model](docs/COPILOT-HARNESS-MODEL.md):** Explains what `softwareFactoryVscode` is meant to be, why it lives in its own repository, and the intended namespace-first integration model.
- **[Harness Integration Specification](docs/HARNESS-INTEGRATION-SPEC.md):** Defines artifact classes, ownership boundaries, and the target install/update contract.
- **[Harness Namespace Migration Mitigation Plan](docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md):** Provides the phased migration plan, Definition of Done, verification steps, and review prompts for moving from hidden-tree installs to namespaced `.copilot` / `.github` integration.
- **[Harness Namespace Implementation Backlog](docs/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md):** Breaks the migration into concrete implementation phases with likely files to change, dependency order, Definition of Done, review criteria, and anti-hallucination guardrails.

The explicit runtime mode selector is `FACTORY_RUNTIME_MODE` in the installed `.factory.env`. `development` remains the deterministic default, while `production` selects the manager-backed fail-closed internal-production profile that surfaces `runtime_mode=production` in `preflight` / `status` and disables silent mock fallback.

### Architecture Notes

The repository uses Architecture Decision Records (ADRs) to document non-trivial design choices and avoid future drift.

For the current long-term direction of installation and namespace strategy, start with:

- **[ADR-012: Copilot-First Namespaced Harness Integration](docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md)**
