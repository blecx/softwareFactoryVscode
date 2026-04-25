# Runtime Monitoring and Diagnostics

This document describes the canonical machine-readable monitoring surface for the current manager-backed runtime model.

Do **not** invent a second monitoring workflow or scrape the human-oriented key/value output when automation needs structured diagnostics. Use the JSON form of the existing lifecycle commands instead.

For the operator decision tree that turns these statuses, reason codes, and shared-mode diagnostics into concrete day-two actions, use [`INCIDENT-RESPONSE.md`](INCIDENT-RESPONSE.md).

## Canonical commands

From the source checkout:

```bash
python3 scripts/factory_stack.py preflight --json
python3 scripts/factory_stack.py status --json
```

From an installed target repository:

```bash
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py preflight --json
python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py status --json
```

These commands stay grounded in the authoritative manager-backed snapshot/readiness contract from `ADR-014`.

- `preflight --json` is the preferred first diagnostic query when you need to know whether the runtime is ready, needs ramp-up, is degraded, or is drifting.
- `status --json` includes the same readiness vocabulary plus the current runtime state, active-workspace facts, rebuild hinting, and install metadata that operators typically need during triage.

## Top-level JSON shape

Both commands emit one JSON object with these stable top-level sections:

- `command` — either `preflight` or `status`
- `authority` — the runtime-truth source (`manager-backed-snapshot-readiness`)
- `notices` — non-fatal operational notes such as recovered registry metadata
- `workspace` — workspace identity and operator-selection facts
- `runtime` — lifecycle/runtime-state facts plus recovery/selection metadata
- `preflight` — normalized readiness result, reason codes, issues, and blocking services
- `diagnostics` — topology, tenant, endpoint-alignment, and port expectations
- `services` — per-service machine-readable runtime diagnostics

## Field highlights

### `workspace`

- `workspace_id`
- `instance_id`
- `target`
- `compose_project`
- `runtime_mode`
- `topology_mode`
- `active`
- `active_workspace`
  - `instance_id`
  - `workspace_id`
  - `is_current`
- `port_index` (`status --json` only)

Use this section to anchor diagnostics to the canonical workspace identity and to understand whether some *other* workspace is currently active.

### `runtime`

- `runtime_state`
- `lifecycle_state`
- `persisted_runtime_state`
- `selection`
- `recovery`
- `last_transition_at`
- `last_transition_reason_codes`
- `installed_version` (`status --json` only)
- `factory_commit` (`status --json` only)
- `lock_commit` (`status --json` only)
- `needs_rebuild` (`status --json` only)

`runtime_state` is the operator-facing current state. `lifecycle_state` and the recovery metadata expose the underlying manager-backed lifecycle and resume classification when relevant.

### `preflight`

- `status`
- `recommended_action`
- `reason_codes`
- `issues`
- `blocking_services`
- `readiness`

This is the normalized readiness contract you should automate against for alerting and day-two triage.

Important semantics:

- `status=ready` means the required services for the selected profile are ready.
- `status=needs-ramp-up` means the runtime needs `start` or `resume`.
- `status=config-drift` means generated/runtime alignment or required config has drifted.
- `status=degraded` means the runtime exists but one or more services are unhealthy enough to block safe use.
- `status=error` is fail-closed output used when status inspection could not obtain the required manager-backed snapshot.

### `diagnostics`

- `runtime_topology`
- `shared_mode_diagnostics`
- `workspace_urls`
- `expected_workspace_urls`
- `manifest_server_urls`
- `manifest_health_urls`
- `expected_service_ports`
- `effective_workspace_urls` (`status --json` only)

This section is the canonical place to inspect topology mode, shared-mode tenant requirements, endpoint drift, and expected port bindings.

### `services`

Each service record contains:

- `status`
- `docker_status`
- `service_kind`
- `scope`
- `topology_mode`
- `workspace_owned`
- `runtime_identity`
- `workspace_server_name`
- `expected_port`
- `published_ports`
- `port_match`
- `discovery_url`
- `probe_url`
- `reason_codes`
- `details`

This is the per-service surface for alerting and affected-service triage. When the manager classifies a service as unhealthy or missing, inspect `reason_codes`, `details`, and the top-level `blocking_services` list together.

## Triage examples

### Alert if the runtime is not ready

```bash
python3 scripts/factory_stack.py preflight --json | jq '.preflight.status'
```

### List affected services and their reason codes

```bash
python3 scripts/factory_stack.py status --json | jq '.services | to_entries[] | select((.value.reason_codes | length) > 0) | {service: .key, status: .value.status, reason_codes: .value.reason_codes}'
```

### Inspect shared-mode tenant requirements

```bash
python3 scripts/factory_stack.py preflight --json | jq '.diagnostics.shared_mode_diagnostics'
```

### Check which workspace is currently active

```bash
python3 scripts/factory_stack.py status --json | jq '.workspace.active_workspace'
```

## Failure handling

If `status --json` cannot obtain the required manager-backed snapshot, the command fails closed and emits structured output with:

- `preflight.status = "error"`
- `preflight.recommended_action = "inspect-registry"`
- the blocking message in `preflight.issues`

That preserves one machine-readable surface even when the authoritative runtime-truth dependency is unavailable.
