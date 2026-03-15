# Installing Software Factory VS Code

This guide provides exactly how to install and bootstrap the `softwareFactoryVscode` capability. 

The Factory is designed to operate seamlessly via a "Hidden-Tree Isolation Model." When installed, it places itself under a `.softwareFactoryVscode/` hidden directory within your target project. It does **not** overwrite or pollute your existing `.vscode/`, `.github/`, or project files.

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
curl -sSL https://raw.githubusercontent.com/blecx/softwareFactoryVscode/main/scripts/install_factory.py | python3

# 4. Bootstrap the local isolation environment
python3 .softwareFactoryVscode/scripts/bootstrap_host.py
```

---

## Scenario 2: Inject into an Existing Project
If you already have a repository and want to attach Factory capabilities to it.

```bash
# 1. Navigate to the root of your existing project
cd /path/to/your/existing-project

# 2. Download and execute the Factory Installer
curl -sSL https://raw.githubusercontent.com/blecx/softwareFactoryVscode/main/scripts/install_factory.py | python3

# 3. Bootstrap the local isolation environment
python3 .softwareFactoryVscode/scripts/bootstrap_host.py
```

> **Note on `.gitignore`**: The bootstrap process creates an environment file and a temporary directory. You should add the following to your project's `.gitignore`:
> ```text
> # Factory Isolation
> .tmp/softwareFactoryVscode/
> .factory.env
> ```

---

## Environment Setup
After running the bootstrap command, a `.factory.env` file is generated in the root of your project. 
Open `.factory.env` and populate any required API keys to activate the backend LLM capability:

```env
# Example .factory.env generated variables
TARGET_WORKSPACE_PATH=/path/to/your/project
PROJECT_WORKSPACE_ID=my-project
COMPOSE_PROJECT_NAME=factory_my-project

# Required for AI/MCP connectivity
CONTEXT7_API_KEY=your_context7_key_here
OPENAI_API_KEY=your_openai_key_here
```

---

## Starting Services
Once installed and bootstrapped, you can start the completely isolated Factory container stack from within the hidden tree:

```bash
cd .softwareFactoryVscode
docker compose -f compose/docker-compose.factory.yml up -d
cd ..
```

---

## Validation Steps
To prove the installation works and the target mounts are successfully connected to your host project:

1. **Verify State**: Confirm that `.factory.lock.json`, `.factory.env`, and the folder `.softwareFactoryVscode/` exist in your root directory.
2. **Verify Containers**: Run `docker ps` to ensure the `factory_my-project` MCP container stack is running smoothly.
3. **Verify Mount**: Connect to one of the containers and confirm your project is mounted to `/target`.
   ```bash
   docker exec -it factory_my-project-[container-name] ls /target
   ```
   You should see your host project files listed.
