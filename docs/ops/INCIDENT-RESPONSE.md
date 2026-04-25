# Incident Response and Day-Two Operator Runbooks

This document is the canonical operator decision tree for the current internal self-hosted, manager-backed runtime contract.

It complements [`MONITORING.md`](MONITORING.md), [`BACKUP-RESTORE.md`](BACKUP-RESTORE.md), [`../PRODUCTION-READINESS.md`](../PRODUCTION-READINESS.md), and [`../INSTALL.md`](../INSTALL.md).

Use only the supported lifecycle, monitoring, verification, backup, restore, and update entrypoints documented here. Do **not** invent a second lifecycle model, fall back to legacy scripts, or capture evidence outside the approved repo/runtime boundaries.

Examples below use the source-checkout command form. When you are operating from an installed target repository, substitute the mirrored `.copilot/softwareFactoryVscode/scripts/...` path for the same command.

## First-response checklist

1. Capture machine-readable readiness and runtime state.
2. Read `preflight.status`, `preflight.recommended_action`, `preflight.reason_codes`, `preflight.blocking_services`, `runtime.runtime_state`, and the affected entries under `services`.
3. Use the least-destructive supported action first.
4. If state must survive a destructive step, enter the bounded `suspended` state and take a supported backup before proceeding.
5. If one bounded repair pass does not recover the runtime, capture escalation evidence and stop improvising.

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

If the workspace is currently `suspended` and `recommended_action=resume`, prefer `resume` over a blind cold start.

## Alert-condition routing

Use this table to map the machine-readable alert surface from PR-08 to the correct runbook.

| Monitoring signal | Typical reason codes / fields | First operator action | Use this runbook |
| --- | --- | --- | --- |
| `preflight.status=needs-ramp-up` with `recommended_action=start` | `no-running-services`, `service-not-running` | Start the runtime from the current baseline | [Startup failure or runtime not ready](#startup-failure-or-runtime-not-ready) |
| `preflight.status=needs-ramp-up` with `recommended_action=resume`, or `runtime.runtime_state=suspended` | `suspend-requested`, `resume-requested` | Resume the bounded suspended runtime | [Restart, suspend/resume, and cleanup](#restart-suspendresume-and-cleanup) |
| `preflight.status=config-drift` | `missing-config`, `missing-secret`, `missing-mount`, `workspace-url-drift`, `manifest-server-url-drift`, `manifest-health-url-drift`, `profile-mismatch` | Correct live config or refresh the generated runtime contract before restarting | [Missing secret, missing config, or config drift](#missing-secret-missing-config-or-config-drift) |
| `preflight.status=degraded` with `recommended_action=repair` | `dependency-unhealthy`, `endpoint-unreachable`, `mcp-initialize-failed`, `service-missing`, `service-unhealthy`, `service-port-mismatch` | Perform a bounded restart or cold-start recovery, then verify | [Unhealthy service or degraded runtime](#unhealthy-service-or-degraded-runtime) |
| `preflight.status=degraded` with `recommended_action=inspect-shared-topology`, or unhealthy `diagnostics.shared_mode_diagnostics` | `shared-service-discovery-missing`, `shared-mode-tenant-enforcement-missing`, `shared-mode-workspace-duplicate`, `identity-mismatch` | Fix the shared-mode topology or tenant identity before restarting | [Shared-mode or tenant-identity misconfiguration](#shared-mode-or-tenant-identity-misconfiguration) |
| `preflight.status=docker-unavailable` or `preflight.status=docker-error` | `docker-unavailable`, `docker-inspection-failed`, `host-docker-unavailable`, `host-network-unavailable`, `host-disk-exhausted` | Recover the host/Docker dependency first; do not loop runtime restarts blindly | [Startup failure or runtime not ready](#startup-failure-or-runtime-not-ready) |
| `preflight.status=error` with `recommended_action=inspect-registry` | `registry-record-missing`, `missing-runtime-metadata`, `unexpected-error`, `terminal-runtime-failure`, `repair-circuit-breaker` | Capture evidence, recover from the installed baseline or last supported backup, and escalate if needed | [Update or rollback failure](#update-or-rollback-failure) and [Escalation evidence capture](#escalation-evidence-capture) |

## Reason-code families and operator actions

Every current runtime reason code is covered by one of these action families.

| Reason codes | Operator action |
| --- | --- |
| `missing-config`, `missing-secret`, `missing-mount`, `workspace-url-drift`, `manifest-server-url-drift`, `manifest-health-url-drift`, `profile-mismatch` | Go to [Missing secret, missing config, or config drift](#missing-secret-missing-config-or-config-drift). Correct the config first; do **not** keep retrying `start` against known drift. |
| `shared-service-discovery-missing`, `shared-mode-tenant-enforcement-missing`, `shared-mode-workspace-duplicate`, `identity-mismatch` | Go to [Shared-mode or tenant-identity misconfiguration](#shared-mode-or-tenant-identity-misconfiguration). Correct topology or tenant identity before restart. |
| `dependency-unhealthy`, `endpoint-unreachable`, `mcp-initialize-failed`, `service-missing`, `service-not-running`, `service-unhealthy`, `service-port-mismatch`, `no-running-services` | Go to [Startup failure or runtime not ready](#startup-failure-or-runtime-not-ready) or [Unhealthy service or degraded runtime](#unhealthy-service-or-degraded-runtime), depending on whether the runtime is absent or degraded in place. |
| `docker-unavailable`, `docker-inspection-failed`, `host-docker-unavailable`, `host-network-unavailable`, `host-disk-exhausted` | Treat this as a host dependency outage. Restore Docker/host health before retrying lifecycle commands. |
| `registry-record-missing`, `missing-runtime-metadata`, `unexpected-error` | Treat this as runtime-contract damage or metadata loss. Capture evidence, recover from the installed baseline or backup, and escalate if one bounded recovery pass fails. |
| `repair-not-implemented`, `repair-reprobe`, `repair-restart`, `repair-recreate`, `repair-dependency`, `repair-reconcile-metadata`, `repair-circuit-breaker`, `terminal-runtime-failure` | These are repair breadcrumbs. Run one bounded recovery path, then escalate if the circuit breaker or terminal failure remains present. |
| `backup-requested`, `restore-requested`, `suspend-requested`, `suspend-requires-ready-runtime`, `resume-requested`, `resume-repair-attempted` | These are lifecycle breadcrumbs. Validate the resulting state with `status --json` and continue with the linked restart or backup/restore runbook. |

## Startup failure or runtime not ready

### Startup diagnosis

- Run `preflight --json`, `status --json`, and `verify_factory_install.py --target <path> --runtime`.
- If `preflight.status=needs-ramp-up` and `recommended_action=start`, the runtime is absent or stopped.
- If `preflight.status=docker-unavailable` or `docker-error`, fix the host dependency first.
- If `preflight.status=config-drift`, switch to the config-drift runbook instead of retrying `start` blindly.

### Startup action

```bash
python3 scripts/factory_stack.py start --build
```

- Use `start --build` for the first recovery attempt after a failed start or a cold runtime.
- If Docker or host prerequisites are unavailable, restore those first; repeated runtime restarts will not fix a dead Docker daemon or a full disk.

### Startup validation

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

### Startup escalation triggers

- the runtime stays at `docker-unavailable`, `docker-error`, or `error` after the host issue is corrected;
- `preflight.reason_codes` still include `missing-runtime-metadata` or `registry-record-missing`; or
- the same startup failure repeats after one bounded restart attempt.

## Unhealthy service or degraded runtime

### Degraded-runtime diagnosis

- Use `status --json` to identify the affected entries under `services`.
- Typical degraded-service signals are `endpoint-unreachable`, `mcp-initialize-failed`, `service-unhealthy`, `service-missing`, `service-port-mismatch`, or `dependency-unhealthy`.
- Use `preflight.blocking_services` as the shortlist of services blocking safe use.

### Degraded-runtime action

Start with the least-destructive restart path:

```bash
python3 scripts/factory_stack.py stop
python3 scripts/factory_stack.py start --build
```

If the runtime still reports the same degraded service and you intentionally want a colder reset of runtime-owned state, escalate once to:

```bash
python3 scripts/factory_stack.py cleanup
python3 scripts/factory_stack.py start --build
```

Use `cleanup` only after deciding that recreating the runtime from the installed baseline is safer than preserving current runtime metadata/data. If state matters, take a supported backup first.

### Degraded-runtime validation

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

### Degraded-runtime escalation triggers

- `repair-circuit-breaker` or `terminal-runtime-failure` appears in the latest reason codes;
- the same service remains in `blocking_services` after one bounded restart/cold-start pass; or
- the degraded service is shared-mode infrastructure and the tenant/topology diagnostics are ambiguous.

### Documented unhealthy-service drill

This runbook is kept honest by repository-backed drill coverage:

- [`../../tests/test_mcp_runtime_manager.py`](../../tests/test_mcp_runtime_manager.py) simulates degraded `endpoint-unreachable` and `mcp-initialize-failed` states and expects the machine-readable reason codes described above.
- [`../../tests/test_throwaway_runtime_docker.py`](../../tests/test_throwaway_runtime_docker.py) proves the bounded `stop` / `start` / `cleanup` recovery path against a real throwaway runtime, including image retention and successful restart.

## Missing secret, missing config, or config drift

### Config-drift diagnosis

- `preflight.status=config-drift` is the canonical signal.
- Read `preflight.reason_codes` to distinguish `missing-secret`, `missing-config`, `missing-mount`, and URL/manifest drift.
- In production mode, expect failures when `CONTEXT7_API_KEY`, a live GitHub credential, or a real `GITHUB_OPS_ALLOWED_REPOS` allowlist is missing or still placeholder-filled.
- `profile-mismatch` means the current runtime contract does not match the selected profile. Do not paper over this with repeated restarts.

### Config-drift action

- Correct the live config in the canonical installed runtime contract under `.copilot/softwareFactoryVscode/`.
- Rebuild the generated runtime contract when the drift is workspace or manifest related.
- Use the supported update helper when the install needs to refresh generated artifacts from the canonical source:

```bash
python3 scripts/factory_update.py check --target <path>
python3 scripts/factory_update.py apply --target <path>
```

- After correcting the config or refreshing the generated artifacts, restart from the current baseline:

```bash
python3 scripts/factory_stack.py stop
python3 scripts/factory_stack.py start --build
```

### Config-drift validation

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

### Config-drift escalation triggers

- drift persists after a supported update/apply plus one bounded restart;
- the install can no longer regenerate `.factory.env` or `.tmp/runtime-manifest.json`; or
- production-mode validation still reports placeholder/blocked config that you cannot correct locally.

## Shared-mode or tenant-identity misconfiguration

### Shared-mode diagnosis

- Inspect `diagnostics.shared_mode_diagnostics` in both `preflight --json` and `status --json`.
- Typical shared-mode failures are `shared-service-discovery-missing`, `shared-mode-tenant-enforcement-missing`, `shared-mode-workspace-duplicate`, and `identity-mismatch`.
- If shared mode is intentional, the diagnostics must show the expected shared URLs and tenant-identity requirements.

### Shared-mode action

- If the workspace should remain per-workspace, remove accidental shared-mode config and restart the runtime.
- If the workspace should run in shared mode, ensure the canonical runtime contract includes the explicit shared discovery URLs and that workspace clients send `X-Workspace-ID=<PROJECT_WORKSPACE_ID>` consistently.
- If duplicate workspace-owned containers appear while shared mode is configured, stop the runtime, correct the topology contract, and start again from the corrected baseline.

```bash
python3 scripts/factory_stack.py stop
python3 scripts/factory_stack.py start --build
```

### Shared-mode validation

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

### Shared-mode escalation triggers

- `tenant_identity_required` remains true but the runtime cannot prove which tenant identity is in use;
- shared-capable services keep oscillating between workspace-owned and shared expectations; or
- cross-tenant isolation cannot be explained with the current diagnostics.

## Restart, suspend/resume, and cleanup

Use the smallest supported lifecycle action that matches the incident.

| Goal | Commands | What is preserved | What is removed |
| --- | --- | --- | --- |
| Planned pause with a later safe return | `python3 scripts/factory_stack.py suspend --completed-tool-call-boundary` then `python3 scripts/factory_stack.py resume` | Runtime metadata, supported data, and the bounded resume-safe boundary | Running containers while suspended |
| Restart while preserving metadata, named volumes, and images | `python3 scripts/factory_stack.py stop` then `python3 scripts/factory_stack.py start --build` | Runtime metadata, named volumes, runtime data, installed baseline, Docker images | Running containers |
| Restart while intentionally dropping named volumes | `python3 scripts/factory_stack.py stop --remove-volumes` then `python3 scripts/factory_stack.py start --build` | Runtime metadata, installed baseline, Docker images | Running containers and named volumes |
| Cold-start from the installed baseline | `python3 scripts/factory_stack.py cleanup` then `python3 scripts/factory_stack.py start --build` | Installed `.copilot/softwareFactoryVscode/` baseline and Docker images | Runtime metadata, workspace-scoped runtime data, containers, named volumes |

Use `cleanup` only when you want to abandon the current runtime metadata/data and rebuild from the installed baseline. If you might need that state later, suspend and back it up first.

## Backup and restore / disaster recovery

### Backup and restore diagnosis

- Supported backup requires the bounded `suspended` lifecycle state.
- Restore accepts only a bundle captured from a `resume-safe` suspended state with `completed_tool_call_boundary=true`.
- Restore is for recovery of supported runtime data and runtime contract artifacts; it is not an alternate update or bootstrap system.

### Backup and restore action

Use the canonical roundtrip sequence:

```bash
python3 scripts/factory_stack.py suspend --completed-tool-call-boundary
python3 scripts/factory_stack.py backup
python3 scripts/factory_stack.py cleanup
python3 scripts/factory_stack.py restore --bundle-path <bundle-dir>
python3 scripts/factory_stack.py resume
python3 scripts/verify_factory_install.py --target <path> --runtime
```

A successful restore leaves the runtime in the bounded `suspended` state. `resume` is the canonical next action.

### Backup and restore validation

- `restore` should report `runtime_state=suspended`, `recommended_action=resume`, `recovery_classification=resume-safe`, and `completed_tool_call_boundary=true`.
- After `resume`, rerun `preflight --json`, `status --json`, and `verify_factory_install.py --target <path> --runtime`.

### Backup and restore escalation triggers

- the bundle fails checksum or workspace-identity validation;
- the bundle is not `resume-safe`; or
- the restored runtime cannot resume to a ready state after one bounded recovery pass.

### Documented backup/restore drill

The repository-backed roundtrip proof lives in [`../../tests/test_throwaway_runtime_docker.py`](../../tests/test_throwaway_runtime_docker.py) and verifies `suspend -> backup -> cleanup -> restore -> resume -> verify` against real runtime data and generated runtime artifacts.

## Update or rollback failure

### Update/rollback diagnosis

- Capture fresh `preflight --json`, `status --json`, and `verify_factory_install.py --target <path> --runtime` output before touching the install.
- If an update or reinstall left the runtime at `config-drift`, `error`, or `runtime-deleted`, treat that as installed-workspace contract damage, not as a cue to hand-edit generated files.

### Update/rollback action

First, use the supported update helper against the target workspace:

```bash
python3 scripts/factory_update.py check --target <path>
python3 scripts/factory_update.py apply --target <path>
```

If the runtime still will not recover and you have a supported backup bundle, use the last known-good bundle to recover the runtime contract and state:

```bash
python3 scripts/factory_stack.py restore --bundle-path <bundle-dir>
python3 scripts/factory_stack.py resume
```

If you do **not** have a supported bundle and the install contract itself is intact, fall back to a cold start from the installed baseline:

```bash
python3 scripts/factory_stack.py cleanup
python3 scripts/factory_stack.py start --build
```

### Update/rollback validation

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
python3 scripts/verify_factory_install.py --target <path> --runtime
```

If the incident includes repository changes or a factory update under review, also run:

```bash
python3 scripts/local_ci_parity.py
```

### Update/rollback escalation triggers

- the updater cannot re-establish the install contract under `.copilot/softwareFactoryVscode/`;
- the runtime still reports `registry-record-missing`, `missing-runtime-metadata`, or `terminal-runtime-failure` after one bounded recovery path; or
- you need a rollback but no supported backup bundle exists.

## Escalation evidence capture

When the incident cannot be closed in one bounded pass, capture this evidence and attach it to the issue/PR or operator handoff:

- raw output from `python3 scripts/factory_stack.py preflight --json`
- raw output from `python3 scripts/factory_stack.py status --json`
- raw output from `python3 scripts/verify_factory_install.py --target <path> --runtime`
- the latest `bundle_path` plus `bundle-manifest.json` if backup/restore is involved
- the exact workspace path, instance ID, compose project, runtime mode, and active reason codes
- `python3 scripts/local_ci_parity.py` output when the incident may reflect a repository regression rather than a local runtime-only problem

Store evidence inside a repo-owned `.tmp/incident-<id>/` directory or the supported backup bundle path. Do **not** move the evidence surface to `/tmp` or any second runtime authority.

## Related references

- [`MONITORING.md`](MONITORING.md) — machine-readable status fields and JSON triage surface
- [`BACKUP-RESTORE.md`](BACKUP-RESTORE.md) — supported backup/restore contract and bundle contents
- [`../CHEAT_SHEET.md`](../CHEAT_SHEET.md) — quick operator reference for lifecycle and validation commands
- [`../PRODUCTION-READINESS.md`](../PRODUCTION-READINESS.md) — canonical readiness contract and final sign-off rules
