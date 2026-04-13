# ⚡ Software Factory Cheat Sheet

A quick operator reference for the current namespace-first runtime model.

## 📋 VS Code tasks you will actually use

Press `Ctrl+Shift+P` (or `Cmd+Shift+P`), choose `Run Task`, then pick:

- `🧭 Runtime: Preflight` — inspect runtime readiness, config drift, and effective endpoint alignment before probing live services
- `🐳 Docker: Build & Start` — build and start the runtime explicitly
- `🛑 Docker: Stop` — stop the current workspace runtime
- `🛂 Verify: Installation Compliance` — validate the namespace-first install contract
- `🩺 Verify: Runtime Compliance` — validate runtime health against generated endpoints
- `🩺 Verify: Runtime Compliance + MCP` — runtime validation plus VS Code MCP endpoint checks
- `✅ Validate: Factory Quality` — run repository lint/format checks

## 💻 Lifecycle commands

From the source checkout, use `scripts/factory_stack.py`.
From an installed target repository, use `.copilot/softwareFactoryVscode/scripts/factory_stack.py`.

```bash
# Inspect whether the workspace is ready, needs ramp-up, is drifting, or degraded
python3 scripts/factory_stack.py preflight

# Start the runtime explicitly
python3 scripts/factory_stack.py start --build

# Stop the runtime without removing workspace runtime data
python3 scripts/factory_stack.py stop

# Stop and remove runtime volumes for the current workspace
python3 scripts/factory_stack.py stop --remove-volumes

# Show registered workspaces and active selection
python3 scripts/factory_stack.py list

# Show current workspace state, effective URLs, and rebuild hinting
python3 scripts/factory_stack.py status

# Refresh generated runtime artifacts and mark the workspace active
python3 scripts/factory_stack.py activate

# Clear only active selection for the current workspace
python3 scripts/factory_stack.py deactivate

# Remove runtime state for the current workspace (destructive)
python3 scripts/factory_stack.py cleanup
```

### What `activate` means now

`activate` is not just a registry toggle.

It refreshes generated runtime artifacts from the canonical installed-workspace contract and then records that workspace as the active one for the current VS Code / Copilot CLI workflow in the host registry. It does **not** start Docker containers by itself.

### What `cleanup` means now

`cleanup` is deeper than a status refresh.

It removes runtime ownership for the current workspace, including registry ownership, generated runtime artifacts, and workspace-scoped runtime data, while leaving the installed `.copilot/softwareFactoryVscode/` baseline in place.

## 🧪 Validation

```bash
# Run the local test suite
python3 -m pytest tests/ -v

# Validate a target install contract
python3 scripts/verify_factory_install.py --target ../my-target-project

# Validate runtime health and generated MCP endpoints
python3 scripts/verify_factory_install.py --target ../my-target-project --runtime --check-vscode-mcp
```

## ⬆️ Updating an installed target workspace

From the **target repository root**:

```bash
# Check whether the installed factory is current
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check

# Apply the update if needed
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py apply

# Re-verify the install contract
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

The updater refreshes:

- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- `.copilot/softwareFactoryVscode/lock.json`
- the generated `software-factory.code-workspace` file when it is still managed-safe to refresh

## 🚑 Troubleshooting

- **Port conflicts or stale state**: run `python3 scripts/factory_stack.py list` first to reconcile obvious stale registry entries, then use `preflight` to see whether the issue is `needs-ramp-up`, `config-drift`, or `degraded`.
- **Config drift**: rerun bootstrap/update or use `activate` to refresh generated runtime artifacts for the selected workspace.
- **Tenant-aware services**: `mcp-memory`, `mcp-agent-bus`, and `approval-gate` carry tenant-aware groundwork, but they are still candidate shared services rather than a generally promoted shared control plane.
