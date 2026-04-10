# Software Factory for VS Code

Welcome to the **Software Factory for VS Code**, a local, AI-powered development environment that seamlessly integrates autonomous agents and advanced Model Context Protocol (MCP) tooling directly into your VS Code workspace.

## Current Release

- **Latest release:** `2.2`
- **Release notes for GitHub:** [`.github/releases/v2.2.md`](.github/releases/v2.2.md)
- **Full changelog:** [`CHANGELOG.md`](CHANGELOG.md)

## What is this project?

This project provides a pre-configured, multi-tenant capable AI agent runtime designed to automate many aspects of the software development lifecycle. By running a local mesh of dockerized MCP servers (spanning memory, GitHub operations, devops, bash gateways, and repository fundamentals), the Software Factory creates a secure and highly capable back-end for your local AI coding assistants.

It transforms a standard repository into an intelligent "Factory" where you can collaborate with AI agents to build, test, and merge code using standardized, repeatable workflows.

## How it integrates in VS Code

The Software Factory is deeply integrated into VS Code to provide a frictionless developer experience:

- **VS Code Tasks:** Built-in tasks (like `🐳 Docker: Build & Start`, `💼 Select Next PR`, or `🚀 Start: Full Stack (Dev)`) power the complete workflow directly from the Command Palette or Terminal menu.
- **Background Lifecycle Management:** The necessary Docker containers are designed to launch automatically when you open the workspace and shut down gracefully when you close the editor, keeping resource usage to a minimum.
- **Native MCP Client:** It exposes standard Model Context Protocol servers to your VS Code AI extensions (like GitHub Copilot), enriching the AI's context with specific repository knowledge, execution capabilities, and isolated memory stores.
- **Interactive Chat Agents:** Work seamlessly via the Copilot Chat interface using specialized agents (e.g., `@queue-backend` or `@queue-phase-2`) to process issues and navigate the codebase.

## Why it improves the development experience

- **Context-Aware AI:** The MCP servers provide your AI assistant with deep, precise knowledge about your specific codebase, deployment patterns, and operational standards.
- **Safe Execution:** The `approval-gate` and restricted `mcp-bash-gateway` securely sandbox AI actions, ensuring that autonomous code modifications or command executions stay within defined safety constraints.
- **Reduced Context Switching:** You can triage issues, read documentation, run smoke tests, and merge PRs within a single, unified IDE experience without constantly tabbing out to GitHub or other external tools.
- **Standardized Workflows:** Through automated workflows, every developer gets the same baseline guardrails and testing tools, significantly increasing code quality and velocity.

## Getting Started

### Prerequisites

To use the Software Factory, you need the following:

- **Visual Studio Code** (latest version).
- **GitHub Copilot extension** installed.
- An active **GitHub Copilot subscription** OR GitHub Copilot configured with a **Custom LLM**.

**Configuring Copilot for the Factory:**

1. Install the [GitHub Copilot extension](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) from the VS Code Marketplace.
2. Sign in with a GitHub account that holds an active Copilot subscription.
3. _(Optional for Custom LLMs)_ If you prefer using a custom LLM instead of the default Copilot models, configure your VS Code settings (e.g., editing `github.copilot.advanced` in `settings.json` or using a compatible proxy extension) to point Copilot towards your custom endpoint.

### Installation

To install and initialize the Software Factory in your target repository, please follow the detailed step-by-step instructions in the installation guide.

➡️ [Read the Installation Guide](docs/INSTALL.md)

### Usage & Documentation

Once installed, check out our user guides to learn how to operate the factory effectively:

- **[User Handout](docs/HANDOUT.md):** A detailed overview of concepts and workflows.
- **[Cheat Sheet](docs/CHEAT_SHEET.md):** Quick reference for common tasks and CLI commands.
- **[Issue Workflow](docs/WORK-ISSUE-WORKFLOW.md):** Learn how to work through issues using Copilot agents.
- **[Copilot Harness Model](docs/COPILOT-HARNESS-MODEL.md):** Explains what `softwareFactoryVscode` is meant to be, why it lives in its own repository, and the intended namespace-first integration model.
- **[Harness Integration Specification](docs/HARNESS-INTEGRATION-SPEC.md):** Defines artifact classes, ownership boundaries, and the target install/update contract.
- **[Harness Namespace Migration Mitigation Plan](docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md):** Provides the phased migration plan, Definition of Done, verification steps, and review prompts for moving from hidden-tree installs to namespaced `.copilot` / `.github` integration.
- **[Harness Namespace Implementation Backlog](docs/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md):** Breaks the migration into concrete implementation phases with likely files to change, dependency order, Definition of Done, review criteria, and anti-hallucination guardrails.

### Architecture Notes

The repository uses Architecture Decision Records (ADRs) to document non-trivial design choices and avoid future drift.

For the current long-term direction of installation and namespace strategy, start with:

- **[ADR-012: Copilot-First Namespaced Harness Integration](docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md)**
