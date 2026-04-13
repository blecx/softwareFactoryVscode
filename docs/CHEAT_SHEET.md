# ⚡ Software Factory Cheat Sheet

A quick reference guide for operating the Software Factory VS Code environment.

## 📋 VS Code Integrated Tasks

Press `Ctrl+Shift+P` (or `Cmd+Shift+P`), type `Run Task`, and select:

- `Docker: Build & Start` — starts the companion Software Factory runtime when a local workspace env contract exists.
- `Docker: Stop` — force-stops the running factory containers.
- `📦 Select Next PR` — picks the next available pull request from the queue to review.
- `🔀 Merge PR` — merges the selected/currently active PR.
- `✅ Validate: Factory Quality` — runs `black`, `flake8`, and `isort` on the codebase.

## 💻 CLI Commands: Factory Stack (`scripts/factory_stack.py`)

If you prefer the terminal, the `factory_stack.py` orchestrator handles all heavy lifting.

```bash
# Start the stack manually (builds images & attaches to the terminal)
python3 scripts/factory_stack.py start --build --foreground

# Stop the stack
python3 scripts/factory_stack.py stop

# Remove stack, volumes, and networks (Fresh start)
python3 scripts/factory_stack.py stop --remove-volumes

# List all active/registered workspaces on your host
python3 scripts/factory_stack.py list

# Clean up stale registry data for the current workspace
python3 scripts/factory_stack.py cleanup
```

## 🧪 Testing & Validation

Verify that your installation is compliant and the stack is isolated.

```bash
# Run the local python test suite (Memory, AgentBus, Runtime Tests)
python3 -m pytest tests/ -v

# Validate Factory Installation structure on a target project
python3 scripts/verify_factory_install.py --target ../my-target-project

# Verify Runtime Compliance (Checks if the docker mesh and MCP endpoints are healthy)
python3 scripts/verify_factory_install.py --target ../my-target-project --runtime --check-vscode-mcp
```

## ⬆️ Updating an Installed Project Repo

If `softwareFactoryVscode` is already installed in a project under
`.copilot/softwareFactoryVscode/`, use the installed updater from the **target
project root**.

### Quick operator flow

```bash
# 1. Check whether the installed factory is current
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check

# 2. Apply the update if one is available
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py apply

# 3. Verify the install contract after the update
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

### What the updater does

- reads the installed release metadata from
  `.copilot/softwareFactoryVscode/lock.json`
- compares the install against the configured source repository
- updates the installed factory checkout in place when needed
- refreshes `.factory.env`, runtime metadata, and `lock.json`
- re-runs installation compliance verification before declaring success

### For a local source checkout

If you want to explicitly point at a local `softwareFactoryVscode` clone:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check \
  --repo-url /path/to/softwareFactoryVscode

python3 .copilot/softwareFactoryVscode/scripts/factory_update.py apply \
  --repo-url /path/to/softwareFactoryVscode
```

### After the update

Use these commands for a quick follow-up check:

```bash
# Confirm the install is now current
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check

# Inspect whether runtime config is ready, drifting, or needs ramp-up
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py preflight
```

## 🚑 Troubleshooting

- **Port Conflicts**: If the factory fails to boot due to port allocation, check `registry.json` locally or run `python3 scripts/factory_stack.py cleanup` to release dangling port mappings.
- **Data Bleeding**: Your data is safe. The backing `AgentBus` and `MemoryStore` enforce `X-Workspace-ID` matching for all FastMCP queries. If an Agent gets a 400 error, the client is missing the context header.
