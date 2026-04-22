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

## 🤖 AI setup quick note

- **VS Code `1.116+`** — GitHub Copilot is built in; sign in and choose `Use AI Features`.
- **Older VS Code releases** — install the GitHub Copilot extension first.
- **All versions** — a GitHub account with Copilot access (paid plan or Copilot Free) is still required.
- **GitHub Pull Requests and Issues** is optional and only needed for PR/issues UI inside VS Code.

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

### What `suspended` means now

The current practical baseline now supports a bounded user-facing `suspended`
runtime state.

Use `factory_stack.py suspend --completed-tool-call-boundary` when pausing on a
completed tool-call boundary, and use `factory_stack.py resume` to re-hydrate
the same runtime.

`status` and `preflight` surface recovery metadata such as
`recovery_classification`, `completed_tool_call_boundary`, and
`last_runtime_action` so operators can distinguish resume-safe,
resume-unsafe, and manual recovery cases.

### Reload / close / reopen semantics

- Reloading VS Code or closing the window does **not** automatically stop the runtime.
- Reopening the workspace later does **not** auto-start the runtime.
- If the foreground task exits while containers still exist, `status` and `preflight` remain the source of truth for runtime state.
- Re-running `factory_stack.py start` while the runtime is already healthy is a reconcile/idempotent action, not a request for a second runtime.

## 🧪 Validation

```bash
# Run the local test suite
python3 -m pytest tests/ -v

# Validate a target install contract
python3 scripts/verify_factory_install.py --target ../my-target-project

# Validate runtime health and generated MCP endpoints
python3 scripts/verify_factory_install.py --target ../my-target-project --runtime --check-vscode-mcp
```

`verify_factory_install.py --runtime` reuses the same manager-backed readiness vocabulary as `preflight` and `status`; any extra endpoint probes are additive evidence only.

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
- **Tenant-aware services**: `mcp-memory`, `mcp-agent-bus`, and `approval-gate` now satisfy the fulfilled `ADR-008` promotion gate for shared mode, while the default supported operator path remains the practical per-workspace baseline.
- **Topology truth**: `preflight` and `status` now emit `topology_mode`. The default is `per-workspace`; if you opt into `FACTORY_SHARED_SERVICE_MODE=shared`, you must also provide `FACTORY_SHARED_MEMORY_URL`, `FACTORY_SHARED_AGENT_BUS_URL`, and `FACTORY_SHARED_APPROVAL_GATE_URL` so the workspace can discover the promoted shared services without owning duplicate local containers.
- **Shared-mode tenant diagnostics**: when `FACTORY_SHARED_SERVICE_MODE=shared`, `preflight`, `status`, and runtime verification now report `shared_mode_status`, whether explicit `X-Workspace-ID` tenant identity is required, and the expected tenant identity from `PROJECT_WORKSPACE_ID`.
- **Tenant mismatch remediation**: if shared mode reports missing or mismatched tenant selectors, send `X-Workspace-ID=<PROJECT_WORKSPACE_ID>` from workspace clients and align any `project_id` selector to that same value before treating the rollout checks as satisfied.

## 🏷 How to read shared-service rollout status

- `open` — one or more ADR-008 rollout tracks still block shared promotion
- `advanced groundwork` — meaningful rollout slices landed, but the final gate is still open
- `fulfilled` — the current default branch now meets this threshold for `mcp-memory`, `mcp-agent-bus`, and `approval-gate`, while shared mode remains deliberate and opt-in
