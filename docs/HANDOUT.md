# 🏭 Software Factory for VS Code - User Handout

Welcome to the **Software Factory for VS Code**. The current supported model is a namespace-first installed workspace plus an explicit runtime lifecycle.

> **Architecture note:** The supported install contract is namespace-first: the harness lives under `.copilot/softwareFactoryVscode/`, the operator entrypoint is `software-factory.code-workspace`, and legacy `.softwareFactoryVscode` artifacts are migration leftovers rather than supported runtime surfaces.

## 🚀 What you are opening

The generated `software-factory.code-workspace` file is the supported VS Code entrypoint for an installed workspace.

That workspace exposes:

1. **Host Project (Root)** — your actual repository.
2. **AI Agent Factory** — the installed harness under `.copilot/softwareFactoryVscode/`.

The runtime contract behind that workspace is generated from:

- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/lock.json`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`

## 🛠 Golden path

### 1. Open the generated workspace

Open `software-factory.code-workspace` from the target repository root.

### 2. Check runtime state before assuming anything

Run the preflight check first:

- VS Code task: `🧭 Runtime: Preflight`
- CLI: `python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py preflight`

Preflight tells you whether the workspace is:

- **ready** — runtime is up and endpoint metadata is aligned
- **needs-ramp-up** — install is fine but containers are not running yet
- **config-drift** — generated workspace/runtime metadata no longer matches the effective contract
- **degraded** — runtime exists but services are missing, unhealthy, or on the wrong ports

### 3. Start the runtime explicitly when needed

Runtime startup is explicit. It is **not** triggered automatically just by opening the workspace.

Use one of:

- VS Code task: `🐳 Docker: Build & Start`
- CLI: `python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py start --build`

### 4. Use activate when switching operator focus

`factory_stack.py activate` does two things:

- refreshes generated runtime artifacts from the canonical installed-workspace contract
- marks that workspace active for the current operator-facing context (for example the VS Code workspace or Copilot CLI session) by recording that selection in the host registry

Activation does **not** start containers by itself.

### 5. Verify the runtime when you need stronger proof

After startup, you can run:

- `python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime`
- `python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime --check-vscode-mcp`

## 🧠 Service model in plain English

The runtime currently uses a hybrid model:

- **workspace-scoped services** stay isolated per workspace because they depend on one repository root or direct project state
- **candidate shared services** such as memory, agent bus, and approval gate carry tenant-aware groundwork, but they are **not yet** treated as a fully promoted shared multi-tenant control plane

That distinction matters: multiple installed workspaces can coexist safely today without pretending every service is already globally shared.

## 🏢 Working with multiple workspaces

You can run multiple installed workspaces on the same host.

Important concepts:

- **installed** — the workspace has a valid namespace-first factory install
- **running** — Docker resources are currently allocated for that workspace
- **active** — the workspace is the one your current VS Code / Copilot CLI workflow is meant to act on, and that selection is recorded in the host registry

Active is an explicit operator choice. It is not a synonym for “owns the default localhost ports.”

Each workspace gets its own effective port block, written into `.copilot/softwareFactoryVscode/.factory.env` and projected into the generated workspace file and runtime manifest.

## 🛑 Shutdown and cleanup

For normal shutdown, use:

- VS Code task: `🛑 Docker: Stop`
- CLI: `python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py stop`

Use `cleanup` only when you intentionally want to remove runtime state for the current workspace. Cleanup is deeper than stop: it removes runtime artifacts, registry ownership, and workspace-scoped runtime data, while leaving the installed `.copilot/softwareFactoryVscode/` baseline in place.
