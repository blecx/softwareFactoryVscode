# Installing Software Factory VS Code

This guide provides exactly how to install and bootstrap the `softwareFactoryVscode` capability.

The Factory is designed to operate seamlessly via a "Hidden-Tree Isolation Model." When installed, it places itself under a `.softwareFactoryVscode/` hidden directory within your target project. It does **not** overwrite or pollute your existing `.vscode/`, `.github/`, or project files.

The supported operating model is **Option B**:

1. Install the factory into the hidden tree.
2. Let the installer/bootstrap generate a host-facing VS Code workspace file.
3. Open that generated workspace file in VS Code to use the installed agents.

This removes ambiguity between "installed successfully" and "usable from VS Code."

## Prerequisites

Before installation, verify you have the following installed on your local host:

- `git`
- `python3` (v3.10+ recommended)
- `docker` and `docker compose`
- VS Code (with the MCP/Copilot extensions if using the AI suite)

---

## Scenario 1: Quick Install (New Project)

If you are starting a completely new software project and want the Factory ready from day one.

```bash
# 1. Create and enter your new project directory
mkdir my-new-project
cd my-new-project

# 2. Initialize a git repository (Required for the factory integrations)
git init

# 3. Download and execute the Factory Installer
curl -sSL https://raw.githubusercontent.com/blecx/softwareFactoryVscode/main/scripts/install_factory.py | python3 - --target "$PWD"
```

The installer will:

- clone the factory into `.softwareFactoryVscode/`
- bootstrap `.factory.env`, `.factory.lock.json`, and `.tmp/softwareFactoryVscode/`
- add recommended runtime ignores to `.gitignore`
- generate `software-factory.code-workspace`
- run `scripts/verify_factory_install.py` as a strict post-install compliance check
- print a non-mutating VS Code smoke prompt you can paste into Copilot Chat

---

## Scenario 2: Inject into an Existing Project

If you already have a repository and want to attach Factory capabilities to it.

```bash
# 1. Run the installer against the target repository
curl -sSL https://raw.githubusercontent.com/blecx/softwareFactoryVscode/main/scripts/install_factory.py | python3 - --target /path/to/your/existing-project
```

The installer applies the same bootstrap and workspace generation steps as Scenario 1.

### Updating an Existing Installation

To refresh an already installed factory tree in place, run the same installer with `--update`:

```bash
curl -sSL https://raw.githubusercontent.com/blecx/softwareFactoryVscode/main/scripts/install_factory.py | python3 - --target /path/to/your/existing-project --update
```

The updater will:

- fetch and fast-forward the installed `.softwareFactoryVscode/` checkout when possible
- preserve host-specific files like `.factory.env`
- preserve a custom `software-factory.code-workspace` unless `--force-workspace` is used
- refresh `.factory.lock.json`
- re-run post-install compliance verification before declaring success

---

## Environment Setup

After running the installer, a `.factory.env` file is generated in the root of your project.
Open `.factory.env` and populate any required API keys to activate the backend LLM capability:

```env
# Example .factory.env generated variables
TARGET_WORKSPACE_PATH=/path/to/your/project
PROJECT_WORKSPACE_ID=my-project
COMPOSE_PROJECT_NAME=factory_my-project

# Required for AI/MCP connectivity
CONTEXT7_API_KEY=your_context7_key_here
```

---

## Starting Services

Once installed and bootstrapped, use the canonical runtime helper inside the hidden tree:

```bash
python3 .softwareFactoryVscode/scripts/factory_stack.py start --build
```

The matching canonical stop path is:

```bash
python3 .softwareFactoryVscode/scripts/factory_stack.py stop
```

The helper preserves the supported runtime contract:

- compose files come from `.softwareFactoryVscode/compose/`
- environment comes from the host-facing `.factory.env`
- startup remains deterministic via `up -d --build --wait --wait-timeout ...`

After starting the stack, you can run runtime compliance verification:

```bash
python3 .softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime
```

Inside VS Code, you can run the matching workspace task from the installed factory folder:

- `🩺 Verify: Runtime Compliance`

If you also want to probe the localhost MCP endpoints configured for VS Code, use:

```bash
python3 .softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime --check-vscode-mcp
```

Inside VS Code, the matching workspace task is:

- `🩺 Verify: Runtime Compliance + MCP`

## Using the Installed Agents in VS Code

Open the generated `software-factory.code-workspace` file from the target repository root.

This workspace includes:

- `.` as **Host Project (Root)**
- `.softwareFactoryVscode` as **AI Agent Factory**

Using the generated workspace file is the supported way to access the installed agent configuration in VS Code.

---

## Validation Steps

The installer already runs a strict compliance check after install/update. To re-run it manually:

```bash
python3 .softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

Inside VS Code, the matching workspace task is:

- `🛂 Verify: Installation Compliance`

To print the non-mutating smoke prompt again without changing the target repository:

```bash
python3 .softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

The verifier checks the hidden-tree installation contract, host runtime files, `.gitignore`, lock metadata, and the Option B workspace entrypoint.

Runtime compliance is a second phase you can run after starting services. It checks the core compose services for the factory runtime and, optionally, the localhost MCP endpoints used by VS Code.

To prove the installation works and the target mounts are successfully connected to your host project:

1. **Verify State**: Confirm that `.factory.lock.json`, `.factory.env`, `software-factory.code-workspace`, and the folder `.softwareFactoryVscode/` exist in your root directory.
2. **Verify Containers**: Run `docker ps` to ensure the `factory_my-project` MCP container stack is running smoothly.
3. **Verify Mount**: Connect to one of the containers and confirm your project is mounted to `/target`.

   ```bash
   docker exec -it factory_my-project-[container-name] ls /target
   ```

   You should see your host project files listed.

4. **Verify VS Code Entry Point**: Open `software-factory.code-workspace` and confirm both the host repository and `.softwareFactoryVscode` appear in the Explorer.

### Non-Mutating Smoke Prompt

After the verifier passes, it prints a read-only smoke prompt you can paste into Copilot Chat.
That prompt is designed to validate the installed workspace experience without modifying the target repository.

When runtime compliance also passes, the verifier prints a second non-mutating runtime smoke prompt focused on service health and endpoint reachability.
