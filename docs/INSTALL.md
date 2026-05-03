# Installing Software Factory VS Code

This guide provides exactly how to install and bootstrap the `softwareFactoryVscode` capability.

The Factory is designed to operate seamlessly via a "Harness Namespace Integration Model." When installed, it places itself under a `.copilot/softwareFactoryVscode/` hidden directory within your target project. It does **not** overwrite or pollute your existing `.vscode/`, `.github/`, or project files.

Use this guide when you need the full install/update/readiness authority. The
primary docs intentionally split roles: [`../README.md`](../README.md) orients
new readers, [`HANDOUT.md`](HANDOUT.md) walks through the first-run operator
path, and [`CHEAT_SHEET.md`](CHEAT_SHEET.md) keeps the terse day-to-day command
surface. This page keeps the long-form baseline in one place so the other
primary docs can summarize and link instead of repeating it verbatim.

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

## Readiness closeout snapshot (what is done vs deferred)

The current default branch closes the MCP harness readiness baseline for the
supported operator story documented in this guide:

- namespace-first install/update under `.copilot/softwareFactoryVscode/`
- explicit lifecycle plus manager-backed `preflight`, `status`, and runtime
  verification vocabulary
- bounded `suspended` / `resume` behavior with recovery metadata at completed
  tool-call boundaries
- practical per-workspace lifecycle proof coverage, with targeted Docker-backed
  evidence where real container/image truth matters
- deliberate shared-mode promotion fulfilled for `mcp-memory`,
  `mcp-agent-bus`, and `approval-gate`

Reproducible closeout evidence for this baseline is:

```text
./.venv/bin/pytest tests/test_regression.py -v
./.venv/bin/python ./scripts/local_ci_parity.py
./.venv/bin/python ./scripts/local_ci_parity.py --mode production
RUN_DOCKER_E2E=1 ./.venv/bin/pytest tests/test_throwaway_runtime_docker.py -k "activate_switch_back_keeps_one_active_workspace" -v
```

The canonical production-grade parity command now carries the blocking Docker
image build lane plus the promoted Docker E2E runtime scenarios
`test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`
and `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`.
`test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace`
remains targeted supplemental evidence when the claim depends on explicit
multi-workspace activation truth.

Still deferred after this readiness pass:

- no release/version bump is implied by these documentation updates alone;
- no claim that every MCP service is globally shared or that shared mode is the
  default operator path; and
- no claim that dynamic profile expansion, image pull/upgrade policy
  automation, or broader orchestration/UI work is already part of the
  supported baseline.

## Internal production boundary and sign-off

The readiness snapshot above documents the current **baseline** only. It is not
the final production claim for this repository.

- The supported production target is **internal self-hosted use** for the
  namespace-first, manager-backed runtime model.
- **External hosted multi-tenant SaaS production remains out of scope.**
- [`docs/PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) is the canonical
  readiness contract for scope, blockers, evidence, and final sign-off rules.
- [`docs/PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) remains
  the implementation roadmap for reaching that contract.

Do not describe the repository as production ready until the blocking internal
production requirements have landed and the final sign-off evidence bundle is
complete, including the canonical production-readiness gate and three
consecutive clean runs.

For local validation, rely on the **four-level mirrored validation contract**. Local-first then GitHub-confirmed semantics are explicit. Execution uses the identical bundle composition and skip logic as the `ci.yml` pipeline; explicit exceptions are governed by the shared resolver rule engine, not ad-hoc script bypasses. Further, all local and remote runs are subject to the **bounded-runtime/watchdog rule**, enforcing a strict 45-minute cap per validation bundle.

- `./.venv/bin/python ./scripts/local_ci_parity.py --level <focused-local|pr-update|merge|production>` is the canonical shared-engine local mirror entrypoint. It prints a stable `key=value` projection of the resolved official bundle structure so operators can see selected bundles, reasons, watchdog budgets, timeout kinds, applicable local-vs-GitHub exceptions, and when `--fresh-checkout` is the exact GitHub-parity replay surface.
- `./.venv/bin/python ./scripts/local_ci_parity.py --level production` is the canonical internal production-readiness gate, surfaced in CI as `Internal Production Gate — Docker Parity & Recovery Proofs`, and includes blocking Docker image builds, the promoted Docker E2E runtime proof lane (including backup/restore roundtrip evidence), required internal-production docs/runbooks presence checks, and a concise sign-off bundle under `.tmp/production-readiness/`.
- `./.venv/bin/python ./scripts/local_ci_parity.py` (no flags) is the legacy faster local precheck (superseded by `--level merge` and `--level pr-update`).
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --production-group <docs-contract|docker-builds|runtime-proofs>` runs one named production-only diagnostic slice at a time without redefining readiness authority; these diagnostic runs are for targeted replay and do **not** refresh the canonical sign-off bundle.
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout` replays that same production gate from a clean git worktree after `./setup.sh`, which is the closest local match to GitHub Actions when you want merge-grade parity evidence before pushing.
- `./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build` remains available as a compatibility alias when you only need the Docker build expansion path without the promoted Docker E2E lane.

In GitHub Actions, production checks are now exposed as diagnosable jobs (`Production Docs Contract`, `Production Docker Build Parity`, and `Production Runtime Proofs`) followed by the canonical aggregate gate (`Internal Production Gate — Docker Parity & Recovery Proofs`). The aggregate gate remains the contract-facing sign-off authority, but CI now refreshes that sign-off bundle from the successful production diagnostics instead of replaying the same production lanes again on the critical path.

The promoted blocking Docker E2E subset inside `--mode production` currently
covers:

- `test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`
- `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`
- `test_throwaway_runtime_backup_restore_roundtrip_recovers_state_and_runtime_contract`

Targeted Docker-backed proofs such as
`test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace`
remain opt-in evidence when a slice depends on additional multi-workspace
runtime truth beyond the promoted production gate.

Every successful `--mode production` run refreshes `.tmp/production-readiness/latest.md`, `.tmp/production-readiness/latest.json`, and the rolling streak history in `.tmp/production-readiness/history.json`. Final sign-off still requires three consecutive **clean** runs from that canonical gate.

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
FACTORY_RUNTIME_MODE=development

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

# Required for github-ops-mcp when FACTORY_RUNTIME_MODE=production
GITHUB_OPS_ALLOWED_REPOS=your-org/your-repo

# Optional: point to an untracked JSON file with a live GitHub Models api_key
# instead of exporting GITHUB_TOKEN / GH_TOKEN / GITHUB_PAT directly.
# LLM_CONFIG_PATH=/absolute/path/to/untracked-llm.json

# Optional shared-service topology override (ADR-008 rollout track)
# Default is per-workspace ownership for mcp-memory, mcp-agent-bus, and approval-gate.
FACTORY_SHARED_SERVICE_MODE=per-workspace
# When FACTORY_SHARED_SERVICE_MODE=shared, provide explicit shared discovery URLs:
# FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030
# FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031
# FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001

# Optional immediate LLM quota tuning
# The default immediate limiter is provider/model aware and computes a shared
# 70% foreground lane plus 30% reserve lane inside the workspace. Only set
# these when you need a stricter local override.
# WORK_ISSUE_QUOTA_CEILING_RPS=0.50
# WORK_ISSUE_FOREGROUND_SHARE=0.70
# WORK_ISSUE_RESERVE_SHARE=0.30
# Optional shared in-flight lease ceiling for the workspace-scoped quota broker.
# GitHub mini buckets default to 2 shared leases; the other current GitHub
# buckets default to 1 unless you override them here.
# WORK_ISSUE_CONCURRENCY_LEASE_LIMIT=2
# Optional stale-waiter TTL for the lineage-fairness queue.
# Keep this short unless you are debugging pathological retry behavior.
# WORK_ISSUE_CONCURRENCY_WAITER_TTL_SECONDS=5
# Live LLM clients share workspace-global broker/limiter state at:
# .copilot/softwareFactoryVscode/.tmp/api-throttle-state.json
# .copilot/softwareFactoryVscode/.tmp/api-throttle.lock
# Parent-run clients automatically attach their run lineage, subagents inherit
# their parent-run lineage, and provider Retry-After / cooldown feedback is
# shared across the provider/model-family/lane scope rather than one role only.
```

The bootstrap step also generates `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`.
That manifest is the effective runtime contract for the installed workspace and includes:

- the workspace instance identity
- the compose project name
- the generated host port map
- the structured factory release/build metadata used for update decisions
- the effective MCP URLs used by the generated workspace settings
- runtime health endpoints used by verification

### Runtime mode selector

The installed workspace runtime now exposes one explicit mode selector through `.copilot/softwareFactoryVscode/.factory.env`:

- `FACTORY_RUNTIME_MODE=development` — the default mode; keeps the current deterministic local workflow and allows the existing mock-friendly behavior.
- `FACTORY_RUNTIME_MODE=production` — selects the manager-backed internal-production runtime profile, surfaces `runtime_mode=production` in `factory_stack.py preflight` / `status`, disables silent mock substitution, and fails closed when required live configuration is missing.

For the supported internal-production boundary, set at least:

```env
FACTORY_RUNTIME_MODE=production
GITHUB_TOKEN=your_live_github_token_here
GITHUB_OPS_ALLOWED_REPOS=your-org/your-repo
CONTEXT7_API_KEY=your_context7_key_here
```

You may provide the GitHub Models credential through `GH_TOKEN`, `GITHUB_PAT`, or a non-placeholder `api_key` in an untracked JSON file referenced by `LLM_CONFIG_PATH` instead of `GITHUB_TOKEN`.

If you use the optional OpenAI image-generation tooling in production mode, also provide a live `OPENAI_API_KEY`; the mock image fallback is disabled in that mode.

Production mode also tightens developer conveniences:

- placeholder values like `your-token-here` and `YOUR_ORG/YOUR_REPO` are rejected by the readiness/verifier path;
- dynamic override files via `LLM_OVERRIDE_PATH` are blocked in production mode; and
- dynamic live-key injection through the agent-bus `bus_set_live_key` flow is development-only.

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
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py stop --remove-volumes
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py suspend --completed-tool-call-boundary
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py resume
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py cleanup
```

These commands distinguish:

- **installed** — the workspace has a valid harness namespace factory install
- **running** — the workspace currently owns Docker runtime resources
- **active** — the workspace the current VS Code / Copilot CLI workflow is meant to act on, recorded explicitly in the host registry

`preflight` and `status` now also print `runtime_mode`, so operators can tell whether the workspace is running in the default deterministic `development` mode or the explicit fail-closed `production` mode.

The current practical baseline now supports a bounded user-facing `suspended`
runtime state. Enter it through `factory_stack.py suspend`, and use
`factory_stack.py resume` to re-hydrate the same workspace runtime.

When a workspace is `suspended`, `status` and `preflight` surface recovery
metadata such as `recovery_classification`,
`completed_tool_call_boundary`, and `last_runtime_action` so operators can tell
whether resume is safe, unsafe, or manual.

Reloading VS Code, closing the window, or reopening later does not silently
stop or start the runtime. Containers continue to exist until an explicit
`stop`/`cleanup` path (or an exit mode that deliberately opts into kill-on-exit
behavior) tears them down.

If the foreground task exits while containers are still present, treat
`status`/`preflight` as the source of runtime truth rather than assuming the
terminal session owned the lifecycle. Running `start` again while the runtime is
already healthy is a reconcile/idempotent action, not a request to create a
second workspace runtime.

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

When `FACTORY_RUNTIME_MODE=production`, the runtime keeps the same manager-backed truth surface but changes the readiness gate:

- the `workspace-production` profile excludes `mock-llm-gateway` from default readiness/startup;
- `verify_factory_install.py --runtime` fails closed when required live production config is missing instead of silently downgrading to the mock gateway; and
- a healthy production run therefore requires the live configuration expected by the selected services before the runtime can report `ready`.

Those production failures now distinguish configuration shape problems from missing secret material:

- `missing-config` covers things like an unreadable `LLM_CONFIG_PATH`, a blocked `LLM_OVERRIDE_PATH`, or placeholder `GITHUB_OPS_ALLOWED_REPOS` values.
- `missing-secret` covers absent or placeholder secret material such as GitHub credentials when the selected production services require them.

Touched audit and diagnostic surfaces also redact secret values instead of printing them back verbatim.

That shared-mode contract now extends beyond discovery: if runtime verification
passes, operators can expect memory, bus child records, and shared-service audit
evidence to remain partitioned by tenant identity rather than mixed in ad hoc
shared tables.

Important: workspaces do **not** start Docker services automatically when they are installed.
Only an explicit `start` command should create running containers.

### Cleanup, metadata, and image-retention semantics

- `factory_stack.py start --build` builds images and starts the workspace containers.
  A later `factory_stack.py start` without `--build` reuses retained local images
  when they are already present.
- `factory_stack.py stop` removes workspace containers only. It retains named
  volumes, generated runtime metadata such as `.factory.env` and the runtime
  manifest, workspace-scoped runtime data, the installed baseline, and Docker images.
- `factory_stack.py stop --remove-volumes` removes workspace containers and named
  volumes, but it still retains generated runtime metadata, the installed baseline,
  and Docker images.
- `factory_stack.py cleanup` removes workspace containers/volumes best-effort,
  registry ownership, generated runtime metadata, and workspace-scoped runtime data,
  while preserving the installed `.copilot/softwareFactoryVscode/` baseline and
  retaining Docker images.
- `delete-runtime` is the policy-driven trigger that shares the same artifact
  effects as `cleanup`; it is not a hidden image-prune path or a separate normal
  operator command.
- If `docker image ls` still shows factory images after `stop` or `cleanup`, that
  is retained build state rather than leaked runtime ownership. Image pruning is a
  separate Docker operator action and is never a hidden side effect of the supported
  lifecycle commands.

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

## Day-two operator docs

Once the install is running, use these canonical operator references for day-two work:

- `docs/ops/INCIDENT-RESPONSE.md` — supported incident-response and operator runbooks
- `docs/ops/MONITORING.md` — machine-readable readiness/status field reference
- `docs/ops/BACKUP-RESTORE.md` — supported backup/restore and disaster-recovery contract

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
