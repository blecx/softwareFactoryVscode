# Installing Software Factory VS Code

This guide provides exactly how to install and bootstrap the `softwareFactoryVscode` capability.

The Factory is designed to operate seamlessly via a "Harness Namespace Integration Model." When installed, it places itself under a `.copilot/softwareFactoryVscode/` hidden directory within your target project. It does **not** overwrite or pollute your existing `.vscode/`, `.github/`, or project files.

The supported operating model is **namespace-first**:

1. Install the factory into the `.copilot` namespace.
2. Let the installer/bootstrap generate a host-facing VS Code workspace file.
3. Open that generated workspace file in VS Code to use the installed agents.

This removes ambiguity between "installed successfully" and "usable from VS Code."

## Supported practical baseline (what this guide promises)

This guide documents the current practical per-workspace baseline:

- namespaced install and update under `.copilot/softwareFactoryVscode/`
- explicit runtime lifecycle (`preflight`, `start`, `stop`, `activate`, `deactivate`, `cleanup`)
- per-workspace verification against generated effective endpoints
- generated `software-factory.code-workspace` as the operator entrypoint

This guide documents the current practical per-workspace baseline **and** the
now-fulfilled `ADR-008` promotion gate for the shared control-plane services
`mcp-memory`, `mcp-agent-bus`, and `approval-gate`.

The default supported operator path remains the namespace-first per-workspace
runtime. Shared multi-tenant promotion is now fulfilled for those services
because the repository has explicit tenant identity enforcement, truthful
topology/runtime diagnostics, tenant-partitioned persistence and audit paths,
and cross-tenant proof coverage for deliberate shared-mode use.

## Shared multi-tenant promotion gate (how to read release/docs status)

Release notes and operator-facing docs in this repository use the same status
words for the ADR-008 shared-service rollout:

- `open` — one or more rollout tracks are still incomplete, so shared
  multi-tenant promotion must be described as still gated.
- `advanced groundwork` — important rollout slices have landed and may be
  called out, but the repository still cannot honestly claim fulfilled shared
  promotion.
- `fulfilled` — only allowed when the full evidence threshold is met and a
  final architecture/documentation review confirms that the claim matches the
  repository's real code and diagnostics.

Before any release or operator guide flips shared multi-tenant promotion to
`fulfilled`, the evidence threshold must be met explicitly:

- tenant identity is enforced end to end for promoted shared mode;
- runtime topology, verification output, and operator diagnostics truthfully
  distinguish shared versus per-workspace behavior;
- storage, logs, metrics, and audit trails are partitioned or labeled by
  tenant identity;
- cross-tenant regression coverage and Docker-backed validation prove the
  isolation contract;
- operator guidance is complete enough for repeatable day-two shared-mode use;
  and
- a final architecture/documentation review against
  `docs/architecture/ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md` and
  `docs/architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md` confirms the
  fulfilled claim.

Until then, keep the wording at `open` or `advanced groundwork` rather than
implying that ADR acceptance alone finished the rollout.

Current default-branch status: `fulfilled` for `mcp-memory`, `mcp-agent-bus`,
and `approval-gate`. Historical releases may still use `open` or `advanced
groundwork` when they describe earlier repository states.

## Prerequisites

Before installation, verify you have the following installed on your local host:

- `git`
- `python3` (v3.10+ recommended)
- `docker` and `docker compose`
- VS Code

### VS Code AI setup by version

For the AI-assisted workflow described in this repository:

- **VS Code `1.116+`** — GitHub Copilot is built in, so no separate marketplace install is required for chat, inline suggestions, or agents.
- **Older VS Code releases** — install the [GitHub Copilot extension](https://marketplace.visualstudio.com/items?itemName=GitHub.copilot) before using AI features.
- **All versions** — sign in with a GitHub account that has Copilot access (paid plan or Copilot Free) before following the Copilot-driven workflow steps.
- **GitHub Pull Requests and Issues** is optional. Install it only if you want GitHub PR/issue UI inside VS Code; it is not required for Copilot chat, inline suggestions, agents, or the generated workspace/runtime contract.
- If `chat.disableAIFeatures` is enabled in VS Code, re-enable AI features before following the AI-driven workflow steps in this guide.

These expectations follow the official [VS Code 1.116 release notes](https://code.visualstudio.com/updates/v1_116) and the [Set up GitHub Copilot in VS Code](https://code.visualstudio.com/docs/copilot/setup) documentation.

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

- clone the factory into `.copilot/softwareFactoryVscode/`
- bootstrap `.copilot/softwareFactoryVscode/.factory.env`, `.copilot/softwareFactoryVscode/lock.json`, and `.copilot/softwareFactoryVscode/.tmp/`
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

The updater operates robustly:

- gracefully spins down active Docker compose containers to release handles (`factory_stack.py stop`)
- removes legacy root-level migration leftovers (`.softwareFactoryVscode/`, `.tmp/softwareFactoryVscode/`, `.factory.env`, `.factory.lock.json`) instead of carrying them forward
- forces upstream synchronization of `.copilot/softwareFactoryVscode/` (commits and stashes dirty files to a `local-backup-<timestamp>` branch if required)
- merges new schema entries into `.copilot/softwareFactoryVscode/.factory.env` while keeping your local overrides (like custom ports and secrets)
- preserves a custom `software-factory.code-workspace` unless `--force-workspace` is used
- refreshes `.copilot/softwareFactoryVscode/lock.json`
- re-runs post-install compliance verification before declaring success

For day-to-day lifecycle management, every install also ships with a dedicated
update helper:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py check
python3 .copilot/softwareFactoryVscode/scripts/factory_update.py apply
```

The `check` command reads the installed release metadata from
`.copilot/softwareFactoryVscode/lock.json`, fetches the latest structured
release manifest from the configured repository source, and reports whether the
install is current, behind, or requires a mandatory schema refresh.

The `apply` command delegates to the canonical installer with `--update`, so it
preserves the existing backup, bootstrap, and verification guarantees.

---

## Environment Setup

After running the installer, a `.factory.env` file is generated at `.copilot/softwareFactoryVscode/.factory.env` inside your project.
Open that file and populate any required API keys to activate the backend LLM capability:

```env
# Example .factory.env generated variables
TARGET_WORKSPACE_PATH=/path/to/your/project
PROJECT_WORKSPACE_ID=my-project
COMPOSE_PROJECT_NAME=factory_my-project
FACTORY_INSTANCE_ID=factory-abc123def456
FACTORY_PORT_INDEX=0
FACTORY_DIR=/path/to/your/project/.copilot/softwareFactoryVscode

PORT_CONTEXT7=3010
PORT_BASH=3011
PORT_FS=3012
PORT_GIT=3013
PORT_SEARCH=3014
PORT_TEST=3015
PORT_COMPOSE=3016
PORT_DOCS=3017
PORT_GITHUB=3018
MEMORY_MCP_PORT=3030
AGENT_BUS_PORT=3031
APPROVAL_GATE_PORT=8001
PORT_TUI=9090

# Required for AI/MCP connectivity
CONTEXT7_API_KEY=your_context7_key_here

# Optional shared-service topology override (ADR-008 rollout track)
# Default is per-workspace ownership for mcp-memory, mcp-agent-bus, and approval-gate.
FACTORY_SHARED_SERVICE_MODE=per-workspace
# When FACTORY_SHARED_SERVICE_MODE=shared, provide explicit shared discovery URLs:
# FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030
# FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031
# FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001
```

The bootstrap step also generates `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`.
That manifest is the effective runtime contract for the installed workspace and includes:

- the workspace instance identity
- the compose project name
- the generated host port map
- the structured factory release/build metadata used for update decisions
- the effective MCP URLs used by the generated workspace settings
- runtime health endpoints used by verification

---

## Starting Services

Once installed and bootstrapped, use the canonical runtime helper inside the hidden tree:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py start --build
```

The matching canonical stop path is:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py stop
```

The helper preserves the supported runtime contract:

- compose files come from `.copilot/softwareFactoryVscode/compose/`
- environment comes from `.copilot/softwareFactoryVscode/.factory.env`
- startup remains deterministic via `up -d --build --wait --wait-timeout ...`

For the current practical baseline, shared-service topology remains **opt-in**.
If you set `FACTORY_SHARED_SERVICE_MODE=shared`, the workspace runtime expects
`FACTORY_SHARED_MEMORY_URL`, `FACTORY_SHARED_AGENT_BUS_URL`, and
`FACTORY_SHARED_APPROVAL_GATE_URL` so `mcp-memory`, `mcp-agent-bus`, and
`approval-gate` can be discovered as shared services instead of being treated as
workspace-owned containers.

When shared-capable services are used in that topology, the persistence contract
is tenant-partitioned: `mcp-memory` and `mcp-agent-bus` persist `project_id`
with every tenant-scoped row, mutation audit records are labeled with the same
tenant identity, and purge/admin helpers only delete rows owned by the matching
tenant selector.

The runtime helper now understands workspace-aware lifecycle commands as well:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py list
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py status
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py preflight
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py activate
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py deactivate
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py suspend --completed-tool-call-boundary
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py resume
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py cleanup
```

These commands distinguish:

- **installed** — the workspace has a valid harness namespace factory install
- **running** — the workspace currently owns Docker runtime resources
- **active** — the workspace the current VS Code / Copilot CLI workflow is meant to act on, recorded explicitly in the host registry

The current practical baseline now supports a bounded user-facing `suspended`
runtime state. Enter it through `factory_stack.py suspend`, and use
`factory_stack.py resume` to re-hydrate the same workspace runtime.

When a workspace is `suspended`, `status` and `preflight` surface recovery
metadata such as `recovery_classification`,
`completed_tool_call_boundary`, and `last_runtime_action` so operators can tell
whether resume is safe, unsafe, or manual.

`activate` refreshes generated runtime artifacts from the canonical installed-workspace contract and then marks that workspace active in the host registry. It does **not** start the Docker runtime by itself.

The `preflight` command is the recommended first check after opening or restoring a VS Code workspace.
It inspects the expected compose services, resolved host ports, generated runtime manifest, and
generated workspace MCP URLs before any live endpoint probing. That lets you tell the difference between:

- **ready** — services are up and the endpoint map is aligned
- **needs-ramp-up** — the installation is fine but the runtime is not running yet
- **config-drift** — generated workspace/runtime metadata no longer matches the effective port contract
- **degraded** — services exist but are missing, unhealthy, or published on the wrong ports

`preflight` and `status` also print a `topology_mode` so operators can tell whether
the workspace is using the default per-workspace runtime or an explicit shared-service
topology for the ADR-008 candidate shared services.

That shared-mode contract now extends beyond discovery: if runtime verification
passes, operators can expect memory, bus child records, and shared-service audit
evidence to remain partitioned by tenant identity rather than mixed in ad hoc
shared tables.

Important: workspaces do **not** start Docker services automatically when they are installed.
Only an explicit `start` command should create running containers.

After starting the stack, you can run runtime compliance verification:

```bash
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime
```

Inside VS Code, you can run the matching workspace task from the installed factory folder:

- `🩺 Verify: Runtime Compliance`

If you also want to probe the localhost MCP endpoints configured for VS Code, use:

```bash
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime --check-vscode-mcp
```

Inside VS Code, the matching workspace task is:

- `🩺 Verify: Runtime Compliance + MCP`

## Using the Installed Agents in VS Code

Open the generated `software-factory.code-workspace` file from the target repository root.

This workspace includes:

- `.` as **Host Project (Root)**
- `.copilot/softwareFactoryVscode` as **AI Agent Factory**

Using the generated workspace file is the supported way to access the installed agent configuration in VS Code.

---

## Validation Steps

The installer already runs a strict compliance check after install/update. To re-run it manually:

```bash
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

Inside VS Code, the matching workspace task is:

- `🛂 Verify: Installation Compliance`

In the generated multi-root workspace, that task must resolve `--target` against the
named **Host Project (Root)** folder, not the factory subtree path.

To print the non-mutating smoke prompt again without changing the target repository:

```bash
python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target .
```

The verifier checks the harness namespace installation contract, host runtime files, `.gitignore`, lock metadata, and the canonical workspace entrypoint.

Runtime compliance is a second phase you can run after starting services. It checks the core compose services for the factory runtime and, optionally, the localhost MCP endpoints used by VS Code.

Runtime compliance starts from the same manager-backed snapshot/readiness contract used by `factory_stack.py preflight` and `factory_stack.py status`. Any deeper HTTP or MCP reachability probes are additive evidence only; they do not redefine readiness behind the manager.

When a workspace is assigned a non-default port block, runtime verification follows the generated effective endpoints from the runtime manifest and generated workspace settings instead of assuming only the historical default localhost ports.

To prove the installation works and the target mounts are successfully connected to your host project:

1. **Verify State**: Confirm that `.copilot/softwareFactoryVscode/lock.json`, `.copilot/softwareFactoryVscode/.factory.env`, `software-factory.code-workspace`, and the folder `.copilot/softwareFactoryVscode/` exist in your repository.
2. **Verify Containers**: Run `docker ps` to ensure the `factory_my-project` MCP container stack is running smoothly.
3. **Verify Mount**: Connect to one of the containers and confirm your project is mounted to `/target`.

   ```bash
   docker exec -it factory_my-project-[container-name] ls /target
   ```

   You should see your host project files listed.

4. **Verify VS Code Entry Point**: Open `software-factory.code-workspace` and confirm both the host repository and `.copilot/softwareFactoryVscode` appear in the Explorer.

### Non-Mutating Smoke Prompt

After the verifier passes, it prints a read-only smoke prompt you can paste into Copilot Chat.
That prompt is designed to validate the installed workspace experience without modifying the target repository.

When runtime compliance also passes, the verifier prints a second non-mutating runtime smoke prompt focused on service health and endpoint reachability.
