# 🏭 Software Factory for VS Code - User Handout

Welcome to the **Software Factory for VS Code**. This platform transforms your local environment into an autonomous, multi-tenant AI development factory. It securely orchestrates agents, memory, and development tools alongside your local code inside a VS Code workspace.

> **Architecture note:** The current runtime implementation still uses a hidden-tree installation model in places, but the intended long-term product direction is documented in [`docs/COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md), [`docs/HARNESS-INTEGRATION-SPEC.md`](HARNESS-INTEGRATION-SPEC.md), and [`ADR-012`](architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md).

## 🚀 Concept Overview

The Factory operates using a **Hybrid Multi-Tenant MCP Architecture**.
When you open a factory-enabled repository, local context is served to LLMs using the Model Context Protocol (MCP). The architecture relies on:

1. **Agent Bus (`mcp-agent-bus`)**: Tracks agent runs, plans, task queues, and validation results across different workspaces safely using tenant isolation (`X-Workspace-ID`).
2. **Memory Store (`mcp-memory`)**: A long-term knowledge graph for your AI agent workspaces.
3. **Local Docker Stack**: Provides isolated containers for git operations, DevOps tools, and filesystem sandboxes.

## 🛠 Getting Started (The Golden Path)

### 1. Booting the Factory

The system is designed to be completely invisible and native to your VS Code workflow:

- Open your VS Code workspace (e.g., using the `workspace.code-workspace` file).
- Open your VS Code workspace (e.g., using the generated `software-factory.code-workspace` file).
- That's it!
- _Magic_: Upon opening the folder, VS Code will automatically start the background task: `Docker: Build & Start`. It runs in the foreground of a hidden background-terminal.

### 2. Instructing the Agents

You interact with the factory via your standard VS Code Copilot Chat.
Because the Factory exposes tools via MCP, you can instruct agents to:

- Read issues and create feature plans.
- Spawn code execution runs (`queue-backend`).
- Write structural modifications and query the knowledge graph.

### 3. Graceful Shutdown

When you close your VS Code window, VS Code automatically terminates the background terminal. This sends a graceful `SIGTERM` to the python orchestrator orchestrator, cleanly stopping the Docker Compose containers so you don't leave orphaned detached resources running on your host machine.

## 🏢 Working in a Multi-Tenant Environment

You can run multiple instances of the software factory simultaneously for different target projects on the exact same host machine. The factory dynamically maps unique port blocks for each workspace and writes them to a `.factory.env` file. Data in the SQLite databases is strictly partitioned by `project_id`.
