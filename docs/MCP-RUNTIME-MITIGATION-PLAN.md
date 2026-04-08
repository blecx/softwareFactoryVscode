# MCP Runtime Hardening Mitigation Plan

This plan resolves the MCP runtime instability findings with an implementation-first sequence.
Each step includes a strict **Definition of Done (DoD)** and a concrete **test/verification method**.

---

## Step 1 — Standardize MCP/runtime endpoint contract

### Goal

Eliminate drift between:

- generated runtime manifests,
- runtime verification probes,
- and what MCP services actually expose in practice.

### Changes

1. Set shared MCP runtime reachability checks (`mcp-memory`, `mcp-agent-bus`) to use `http://127.0.0.1:<port>/mcp`.
2. Keep `approval-gate` on `/health` and `mock-llm-gateway` on `/admin/mocks`.
3. Update `scripts/factory_workspace.py` and `scripts/verify_factory_install.py` to use the same endpoint map.
4. Keep `allow_http_error=True` only for MCP stream endpoints where `4xx` may still indicate a reachable server.

### Definition of Done

- `factory_workspace` and `verify_factory_install` use a consistent endpoint contract.
- Tests asserting runtime probe URLs pass with `/mcp` for memory/bus.

### Test this step

- `pytest tests/test_factory_install.py::test_verify_runtime_uses_generated_workspace_endpoint_settings -v`
- `pytest tests/test_factory_install.py::test_runtime_smoke_prompt_uses_generated_endpoint_language -v`

---

## Step 2 — Decouple dynamic host ports from container internal ports

### Goal

Prevent dynamic host port blocks from changing internal service bind ports used by compose-network traffic.

### Changes

1. In `compose/docker-compose.factory.yml`, remove internal port env overrides from shared services:
   - `MEMORY_MCP_PORT`
   - `AGENT_BUS_PORT`
   - `APPROVAL_GATE_PORT`
2. Keep published host ports dynamic via `${MEMORY_MCP_PORT}:3030`, `${AGENT_BUS_PORT}:3031`, `${APPROVAL_GATE_PORT}:8001`.
3. Preserve container-to-container URLs on fixed internal ports:
   - `http://mcp-memory:3030`
   - `http://mcp-agent-bus:3031`
   - `http://approval-gate:8001`

### Definition of Done

- Shared services no longer bind internal ports from workspace-specific host env values.
- Existing inter-service URLs remain fixed and valid.

### Test this step

- `pytest tests/test_factory_install.py::test_runtime_compose_shared_services_do_not_override_internal_ports -v`
- `pytest tests/test_factory_install.py::test_runtime_compose_interservice_urls_use_fixed_internal_ports -v`

---

## Step 3 — Ensure image import/runtime compatibility

### Goal

Remove startup crash loops caused by package/import mismatch.

### Changes

1. Keep all FastMCP Docker images pinned to a known-good version (`mcp==1.25.0`).
2. Keep `docker/agent-worker/Dockerfile` importing `factory_runtime` as a package root.
3. Add test coverage enforcing MCP version consistency across Dockerfiles.

### Definition of Done

- MCP Dockerfiles all reference the same supported `mcp` version.
- Agent worker launches using `factory_runtime.agents.factory_cli` pathing.

### Test this step

- `pytest tests/test_factory_install.py::test_runtime_mcp_dockerfiles_pin_fastmcp_compatible_version -v`
- `pytest tests/test_factory_install.py::test_runtime_dockerfiles_copy_from_factory_runtime_tree -v`

---

## Step 4 — Add golden Docker throwaway regression test

### Goal

Add one end-to-end regression proving the full workflow under a non-default port block.

### Changes

1. Add a Docker-enabled integration test that:
   - creates a fresh throwaway target,
   - forces non-default port allocation (by pre-seeding registry index 0),
   - runs `scripts/validate_throwaway_install.py --keep-target-running`,
   - loads generated workspace settings URLs,
   - verifies real localhost MCP reachability for those exact URLs.
2. Mark the test as Docker-gated (`RUN_DOCKER_E2E=1`).
3. Ensure robust cleanup with `factory_stack.py stop` in `finally`.

### Definition of Done

- New integration test exists and is deterministic.
- It asserts `runtime-manifest.port_index != 0` and probes generated MCP URLs.
- It can be run on Docker-capable machines without manual patching.

### Test this step

- `RUN_DOCKER_E2E=1 pytest tests/test_throwaway_runtime_docker.py -v -s`

---

## Step 5 — Remove local debug artifacts from source tree

### Goal

Prevent accidental dependency on ad-hoc scripts/tests and keep repository clean.

### Changes

Delete temporary debug files added during investigation:

- `debug_data_dirs.py`
- `fix_health.py`
- `patch_compose.py`
- `patch_probe.py`
- `patch_verify.py`
- `test_dump.py`
- `tests/test_e2e_todo_app.py` (experimental, non-canonical test path)

### Definition of Done

- `git status` shows only intentional production/test changes.
- No ad-hoc patch/debug scripts remain tracked.

### Test this step

- `git status --short`

---

## Step 6 — Final validation pass

### Goal

Prove the mitigation is stable at unit + contract levels, plus optional Docker E2E.

### Required validations

1. `pytest tests/test_factory_install.py -v`
2. `pytest tests/test_regression.py -v`

### Optional (Docker-capable host)

3. `RUN_DOCKER_E2E=1 pytest tests/test_throwaway_runtime_docker.py -v -s`

### Definition of Done

- Required tests pass.
- Docker-gated golden test passes when enabled.
- No unresolved endpoint/port-contract mismatch remains in code or tests.
