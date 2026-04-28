# 🏭 Software Factory for VS Code - User Handout

Welcome to the **Software Factory for VS Code**. The current supported model is a namespace-first installed workspace plus an explicit runtime lifecycle.

> **Architecture note:** The supported install contract is namespace-first: the harness lives under `.copilot/softwareFactoryVscode/`, the operator entrypoint is `software-factory.code-workspace`, and legacy `.softwareFactoryVscode` artifacts are migration leftovers rather than supported runtime surfaces.

This handout is the guided first-run path: it shows the order most operators
actually follow after opening an installed workspace. It intentionally
summarizes the deeper install/update/readiness detail in
[`INSTALL.md`](INSTALL.md) and points repeat operators to
[`CHEAT_SHEET.md`](CHEAT_SHEET.md) for terse command lookup.

## 🚀 What you are opening

The generated `software-factory.code-workspace` file is the supported VS Code entrypoint for an installed workspace.

That workspace exposes:

1. **Host Project (Root)** — your actual repository.
2. **AI Agent Factory** — the installed harness under `.copilot/softwareFactoryVscode/`.

The runtime contract behind that workspace is generated from:

- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/lock.json`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`

## 🤖 AI feature setup by VS Code version

This handout keeps the short onboarding version. For the full editor-side setup
details and version-specific caveats, see [`INSTALL.md`](INSTALL.md).

- **VS Code `1.116+`** ships GitHub Copilot built in. Use the Copilot status item or Accounts menu to sign in and enable AI features.
- **Older VS Code releases** still need the GitHub Copilot extension installed before the AI workflow in this handout will work.
- **All versions** still require a GitHub account with Copilot access (paid plan or Copilot Free) for the default AI experience.
- The **GitHub Pull Requests and Issues** extension is optional. Install it only if you want GitHub PR/issue UI inside VS Code; it is not required for Copilot chat, inline suggestions, or agents.

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

### 4.5 Reload, close, and reopen do not invent a second lifecycle

- Reloading VS Code or closing the window does **not** automatically stop the runtime.
- Reopening the workspace later does **not** auto-start the runtime either.
- If the foreground task exits while Docker containers keep running, use `factory_stack.py status` or `factory_stack.py preflight` as the source of runtime truth.
- Running `factory_stack.py start` again while the runtime is already healthy is a reconcile/idempotent action, not a second workspace runtime.

### 5. Verify the runtime when you need stronger proof

After startup, you can run:

- `python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime`
- `python3 .copilot/softwareFactoryVscode/scripts/verify_factory_install.py --target . --runtime --check-vscode-mcp`

These verifier commands use the same manager-backed readiness vocabulary as `preflight` and `status`. Any extra endpoint probes are additive evidence only, so the verifier can deepen the diagnosis without inventing a second runtime-truth authority.

### 5.5 Use the operator runbooks when you need concrete action

When you move from overview to action, go straight to these runbooks instead of
searching around the docs tree:

- [`docs/ops/MONITORING.md`](ops/MONITORING.md) — machine-readable diagnostics,
  `preflight --json` / `status --json` field guidance, and monitoring intent.
- [`docs/ops/INCIDENT-RESPONSE.md`](ops/INCIDENT-RESPONSE.md) — the supported
  day-two decision tree for startup failure, degraded services, config drift,
  suspend/resume, and escalation.
- [`docs/ops/BACKUP-RESTORE.md`](ops/BACKUP-RESTORE.md) — the supported
  backup/restore preconditions and bounded recovery roundtrip.

## 🧠 Service model in plain English

This handout keeps the short operator summary. For the full ADR-008 rollout
vocabulary, evidence threshold, and release/readiness wording rules, see
[`INSTALL.md`](INSTALL.md) and [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md).

The runtime currently uses a hybrid model:

- **workspace-scoped services** stay isolated per workspace because they depend on one repository root or direct project state
- **shared-capable control-plane services** such as memory, agent bus, and approval gate now satisfy the fulfilled `ADR-008` promotion gate for deliberate shared-mode use, while the default operator path remains the practical per-workspace baseline

That distinction matters: multiple installed workspaces can coexist safely today without pretending every service is already globally shared.

Release notes and operator docs still use the same ADR-008 promotion
vocabulary: `open`, `advanced groundwork`, and `fulfilled`. The current
default branch now meets this threshold for `mcp-memory`, `mcp-agent-bus`, and
`approval-gate`; shared mode remains deliberate and opt-in rather than
mandatory for every workspace.

## 🏁 Internal production contract

The supported production target for this repository is **internal self-hosted
use** only.

- **External hosted multi-tenant SaaS production is out of scope.**
- [`docs/PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) is the canonical
  operator-facing readiness contract.
- [`docs/PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) is the
  implementation roadmap for satisfying that contract.
- This handout is the short operator summary; use those two pages when you need
  the contract language or the active supporting plan.
- The readiness baseline described in this handout is necessary, but it is not
  the final production claim. Final sign-off still requires the blocking
  readiness gates and three consecutive clean runs recorded by the canonical
  production-readiness flow.

## ✅ Readiness closeout boundaries

This handout documents the current default-branch readiness baseline. It does
not turn every future runtime-manager idea into a supported promise. For the
full closeout snapshot, sign-off nuance, and supporting detail, see
[`INSTALL.md`](INSTALL.md) and [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md).

For a quick operator proof bundle, pair the guidance here with:

- `./.venv/bin/pytest tests/test_regression.py -v`
- `./.venv/bin/python ./scripts/local_ci_parity.py`
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`
- targeted `RUN_DOCKER_E2E=1` lifecycle proofs when real container/image truth
  matters

The canonical production-grade parity command now includes the promoted
strict-tenant and stop/cleanup Docker E2E runtime proofs. Keep the extra
`RUN_DOCKER_E2E=1` command for targeted scenarios such as explicit
multi-workspace activation / switch-back evidence only.

Still deferred after this readiness pass:

- dynamic profile expansion during a running prompt;
- image pull/upgrade policy automation and broader orchestration/event/UI work;
- any claim of shared-service maturity beyond the explicit `mcp-memory`,
  `mcp-agent-bus`, and `approval-gate` proofs already called out in repository
  docs.

## 🏢 Working with multiple workspaces

You can run multiple installed workspaces on the same host.

Important concepts:

- **installed** — the workspace has a valid namespace-first factory install
- **running** — Docker resources are currently allocated for that workspace
- **active** — the workspace is the one your current VS Code / Copilot CLI workflow is meant to act on, and that selection is recorded in the host registry

Active is an explicit operator choice. It is not a synonym for “owns the default localhost ports.”

Each workspace gets its own effective port block, written into `.copilot/softwareFactoryVscode/.factory.env` and projected into the generated workspace file and runtime manifest.

For the terse lifecycle command list, troubleshooting shortcuts, and cleanup
matrix, jump to [`CHEAT_SHEET.md`](CHEAT_SHEET.md).

## 🛑 Shutdown and cleanup

For normal shutdown, use:

- VS Code task: `🛑 Docker: Stop`
- CLI: `python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py stop`

Use `cleanup` only when you intentionally want to remove runtime state for the current workspace. Cleanup is deeper than stop: it removes runtime artifacts, registry ownership, and workspace-scoped runtime data, while leaving the installed `.copilot/softwareFactoryVscode/` baseline in place. For the fuller stop/cleanup/image-retention matrix, see [`CHEAT_SHEET.md`](CHEAT_SHEET.md).
