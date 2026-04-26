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

## 🚦 Immediate LLM quota policy

- The immediate LLM limiter now chooses a shared workspace quota bucket from the active provider/model family instead of hard-coding one ultra-conservative global default.
- This section documents the bounded immediate-repair baseline from umbrella `#139`; the long-term multi-requester quota-governance contract now lives in `docs/architecture/ADR-015-Quota-Governance-Contract-for-Multi-Requester-LLM-Access.md` and `factory_runtime/agents/tooling/quota_governance.py`.
- Current GitHub Models fallbacks are intentionally modest and split into a shared **70% foreground lane / 30% reserve lane**:
  - `gpt-4o-mini` / `gpt-4.1-mini` families → `0.50 RPS` ceiling (`0.35` foreground / `0.15` reserve)
  - `gpt-4o` / `gpt-4.1` families → `0.30 RPS` ceiling (`0.21` foreground / `0.09` reserve)
  - `o1` / `o3` / `o4` reasoning families → `0.15 RPS` ceiling (`0.105` foreground / `0.045` reserve)
- Override the shared ceiling only when you need a stricter local cap:
  - `WORK_ISSUE_QUOTA_CEILING_RPS`
  - `WORK_ISSUE_FOREGROUND_SHARE`
  - `WORK_ISSUE_RESERVE_SHARE`
- `#141` layers a workspace-scoped quota broker on top of that same shared baseline. Live parent-agent and subagent LLM clients now enter one brokered admission path that reserves both request-rate slots and shared provider/model-family concurrency leases before an outbound provider call is sent.
- `#142` extends that broker with requester-lineage fairness and shared provider-feedback handling. Parent-run LLM clients now carry their `run_id` into quota admission, subagents consume the same parent lineage instead of opening independent provider budget, and queued parent-run / interactive waiters take priority over queued child/background traffic when shared capacity returns.
- Child fan-out is intentionally bounded: one parent lineage can hold only one active shared subagent concurrency lease at a time, so a burst of child calls cannot quietly multiply into unrelated provider entitlement.
- The broker still stores its shared state under `.copilot/softwareFactoryVscode/.tmp/api-throttle-state.json`, guarded by `.copilot/softwareFactoryVscode/.tmp/api-throttle.lock`, so a fresh client instance cannot quietly sprint past the shared budget or bypass the shared in-flight lease ceiling.
- Current default shared concurrency lease ceilings are intentionally conservative: GitHub mini buckets default to `2` shared in-flight leases, while the other current GitHub buckets default to `1`. Override them only when you have a measured reason:
  - `WORK_ISSUE_CONCURRENCY_LEASE_LIMIT`
- Provider `Retry-After` / `429` feedback now lands in a shared provider/model-family/lane scope, so every requester in that budget observes the same cooldown instead of only the role that first triggered the backoff.
- `#143` adds operator-visible load/saturation telemetry for the long-term brokered architecture. `request_diagnostics.summary` now exposes `lease_grant_count`, `lease_denial_count`, `lease_wait_event_count`, `saturation_event_count`, `waiter_count`, `max_waiter_count`, `saturated_lease_scope_count`, and `oldest_waiter_seconds_max` so contention can be audited without inventing a second monitoring stack.
- The long-term contract keeps those shared lanes as delegated workspace/run/requester budget partitions, not per-process entitlements and not a second runtime-truth surface.
- Startup diagnostics now expose `request_quota_policy`, `role_request_policies`, and `request_diagnostics` via `LLMClientFactory.get_startup_report()` so operators can confirm the effective bucket (including `concurrency_lease_limit`) and see whether time is being burned in queue wait, upstream processing, retry-after hints, shared cooldown windows, or fairness protections such as `priority_wait_event_count` / `subagent_parallelism_cap_hits`.
- `request_diagnostics.channels` now include requester-class evidence (`last_requester_class`, `last_lineage_id`, `requester_class_counts`), while `request_diagnostics.shared_scopes` and `request_diagnostics.concurrency_leases` expose the shared feedback scope and lineage-fairness lease counters directly, including `max_waiter_count`, `oldest_waiter_seconds`, `lease_denial_count`, `saturation_event_count`, `saturated`, and `saturation_ratio`.
- `scripts/work-issue.py` now prints the same limiter summary at startup and after execution, including work-issue retry/backoff totals for the current run.

## 💻 Lifecycle commands

From the source checkout, use `scripts/factory_stack.py`.
From an installed target repository, use `.copilot/softwareFactoryVscode/scripts/factory_stack.py`.

```bash
# Inspect whether the workspace is ready, needs ramp-up, is drifting, or degraded
python3 scripts/factory_stack.py preflight

# Emit the same readiness surface as machine-readable JSON
python3 scripts/factory_stack.py preflight --json

# Start the runtime explicitly
python3 scripts/factory_stack.py start --build

# Stop the runtime containers and retain runtime metadata, volumes, and images
python3 scripts/factory_stack.py stop

# Stop the runtime containers and remove named volumes; images still remain
python3 scripts/factory_stack.py stop --remove-volumes

# Show registered workspaces and active selection
python3 scripts/factory_stack.py list

# Show current workspace state, effective URLs, and rebuild hinting
python3 scripts/factory_stack.py status

# Emit the same runtime/status surface as machine-readable JSON
python3 scripts/factory_stack.py status --json

# Refresh generated runtime artifacts and mark the workspace active
python3 scripts/factory_stack.py activate

# Clear only active selection for the current workspace
python3 scripts/factory_stack.py deactivate

# Remove runtime state for the current workspace (destructive to metadata/data, not images)
python3 scripts/factory_stack.py cleanup
```

### What `activate` means now

`activate` is not just a registry toggle.

It refreshes generated runtime artifacts from the canonical installed-workspace contract and then records that workspace as the active one for the current VS Code / Copilot CLI workflow in the host registry. It does **not** start Docker containers by itself.

### What `cleanup` means now

`cleanup` is deeper than a status refresh.

It removes runtime ownership for the current workspace, including registry ownership, generated runtime artifacts, and workspace-scoped runtime data, while leaving the installed `.copilot/softwareFactoryVscode/` baseline in place.

It also removes workspace containers and named volumes best-effort, but it does
**not** prune Docker images.

### Cleanup / image retention semantics

- `start --build` builds images; a later `start` without `--build` reuses retained local images when available.
- `stop` removes workspace containers only and retains named volumes, runtime metadata, and Docker images.
- `stop --remove-volumes` removes containers and named volumes, but still retains runtime metadata and Docker images.
- `cleanup` removes live runtime ownership, generated runtime metadata, and workspace-scoped runtime data while preserving the installed baseline and retaining Docker images.
- `delete-runtime` is the policy-driven trigger with the same artifact effects as `cleanup`; it is not a hidden image-prune path.
- Retained images after `stop` or `cleanup` are expected build cache/state, not leaked runtime ownership.

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

### Runtime modes

- `FACTORY_RUNTIME_MODE=development` is the default and preserves the current deterministic local workflow.
- `FACTORY_RUNTIME_MODE=production` selects the manager-backed `workspace-production` profile.
- `preflight` and `status` surface the effective mode as `runtime_mode=development|production`.
- Production mode excludes `mock-llm-gateway` from default readiness/startup and fails closed when required live config is missing.
- For the current internal-production boundary, populate at least `GITHUB_TOKEN` and `CONTEXT7_API_KEY` before expecting `preflight` / `verify_factory_install.py --runtime` to report ready.
- `GITHUB_OPS_ALLOWED_REPOS` must contain real `owner/repo` values in production mode; placeholder allowlists are rejected.
- You can use `GH_TOKEN`, `GITHUB_PAT`, or an untracked JSON file referenced by `LLM_CONFIG_PATH` instead of `GITHUB_TOKEN` for the GitHub Models credential path.
- If OpenAI image generation is used in production mode, provide `OPENAI_API_KEY`; the mock image fallback is disabled there.
- `LLM_OVERRIDE_PATH` override files and agent-bus `bus_set_live_key` live-key injection are development-only; production mode blocks them.
- Touched audit/diagnostic surfaces redact secret values, and production readiness distinguishes `missing-config` from `missing-secret` outcomes.

### Machine-readable monitoring

- `preflight --json` and `status --json` are the canonical structured diagnostics surfaces for alerting and automation.
- They stay grounded in the same manager-backed snapshot/readiness authority as the text output; there is no second monitoring truth surface.
- Use `status --json` when you need runtime-state, active-workspace, and rebuild metadata in addition to readiness.
- Use `preflight --json` as the fastest readiness/config-drift probe.
- See [`docs/ops/MONITORING.md`](ops/MONITORING.md) for field layout and `jq` examples.

### Day-two runbooks

- [`docs/ops/INCIDENT-RESPONSE.md`](ops/INCIDENT-RESPONSE.md) — diagnosis/action/validation/escalation playbooks for startup failure, degraded services, config drift, shared mode, backup/restore, and update failure.
- [`docs/ops/MONITORING.md`](ops/MONITORING.md) — machine-readable field reference for `preflight --json` and `status --json`.
- [`docs/ops/BACKUP-RESTORE.md`](ops/BACKUP-RESTORE.md) — supported backup/restore preconditions, bundle contents, and roundtrip contract.

## 🧪 Validation

```bash
# Default faster local parity baseline (Docker build parity stays a warning-only skip here)
./.venv/bin/python ./scripts/local_ci_parity.py

# Canonical internal production gate — Docker parity & recovery proofs (blocking Docker image builds + promoted Docker E2E runtime proofs + sign-off bundle)
./.venv/bin/python ./scripts/local_ci_parity.py --mode production

# Focused long-term quota-governance load / contention evidence
./.venv/bin/pytest tests/test_quota_load_validation.py tests/test_quota_broker.py tests/test_llm_quota_policy.py -q

# Compatibility alias for the Docker build expansion path only (no promoted Docker E2E lane)
./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build

# Run the local test suite
python3 -m pytest tests/ -v

# Validate a target install contract
python3 scripts/verify_factory_install.py --target ../my-target-project

# Validate runtime health and generated MCP endpoints
python3 scripts/verify_factory_install.py --target ../my-target-project --runtime --check-vscode-mcp
```

`verify_factory_install.py --runtime` reuses the same manager-backed readiness vocabulary as `preflight` and `status`; any extra endpoint probes are additive evidence only.

## 🏁 Internal production contract

- The supported production target is **internal self-hosted use** for the
  current namespace-first, manager-backed runtime model.
- **External hosted multi-tenant SaaS production is out of scope.**
- [`docs/PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) is the canonical
  readiness contract; this cheat sheet is only a summary surface.
- The current default branch has a strong readiness baseline, but the final
  production claim still requires the blocking readiness gates and three
  consecutive clean runs defined in the contract.

## ✅ Readiness closeout evidence

Use this bundle when a closeout note needs reproducible proof for the current
baseline:

```bash
./.venv/bin/pytest tests/test_regression.py -v
./.venv/bin/python ./scripts/local_ci_parity.py
./.venv/bin/python ./scripts/local_ci_parity.py --mode production
RUN_DOCKER_E2E=1 ./.venv/bin/pytest tests/test_throwaway_runtime_docker.py -k "activate_switch_back_keeps_one_active_workspace" -v
```

This evidence bundle proves the practical baseline plus the promoted production
gate for `test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`,
`test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`, and
`test_throwaway_runtime_backup_restore_roundtrip_recovers_state_and_runtime_contract`.
The extra `RUN_DOCKER_E2E=1` command keeps
`test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace`
available as targeted supplemental evidence when multi-workspace activation
truth matters. It does **not** silently promote every future runtime-management
idea into the supported baseline.

Each canonical `--mode production` run also refreshes `.tmp/production-readiness/latest.md`, `.tmp/production-readiness/latest.json`, and `.tmp/production-readiness/history.json` so operators can track the required three consecutive clean runs for final internal sign-off.

Still deferred after this readiness pass:

- dynamic profile expansion during a running prompt
- image pull/upgrade policy automation
- broader orchestration/event/UI work beyond the accepted ADR baseline
- blanket claims that every service is globally shared by default

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
