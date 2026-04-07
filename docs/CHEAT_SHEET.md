# ⚡ Software Factory Cheat Sheet

A quick reference guide for operating the Software Factory VS Code environment.

## 📋 VS Code Integrated Tasks
Press `Ctrl+Shift+P` (or `Cmd+Shift+P`), type `Run Task`, and select:

| Task Name | Description |
|-----------|-------------|
| `Docker: Build & Start` | (Runs automatically on startup) Boots the MCP services in the background. |
| `Docker: Stop` | Force-stops the running factory containers. |
| `📦 Select Next PR` | Picks the next available pull request from the queue to review. |
| `🔀 Merge PR` | Merges the selected/currently active PR. |
| `✅ Validate: Factory Quality` | Runs `black`, `flake8`, and `isort` on the codebase. |

## 💻 CLI Commands: Factory Stack (`scripts/factory_stack.py`)
If you prefer the terminal, the `factory_stack.py` orchestrator handles all heavy lifting.

```bash
# Start the stack manually (builds images & attaches to the terminal)
python3 scripts/factory_stack.py start --build --foreground

# Stop the stack
python3 scripts/factory_stack.py stop

# Remove stack, volumes, and networks (Fresh start)
python3 scripts/factory_stack.py stop -v

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

## 🚑 Troubleshooting
- **Port Conflicts**: If the factory fails to boot due to port allocation, check `registry.json` locally or run `python3 scripts/factory_stack.py cleanup` to release dangling port mappings.
- **Data Bleeding**: Your data is safe. The backing `AgentBus` and `MemoryStore` enforce `X-Workspace-ID` matching for all FastMCP queries. If an Agent gets a 400 error, the client is missing the context header.
