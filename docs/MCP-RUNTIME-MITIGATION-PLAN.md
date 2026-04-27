# MCP Runtime Mitigation Plan

## Status

Historical sequencing / completed mitigation history. The supported readiness baseline closed the robustness gaps tracked here, so this file remains as traceability and closeout context rather than a current execution plan. Use `docs/PRODUCTION-READINESS.md`, `docs/PRODUCTION-READINESS-PLAN.md`, accepted ADRs, and verified code for the current contract.

This plan replaces the earlier implementation-first checklist with a findings-driven mitigation sequence.
The fresh throwaway install path is green, but the review found remaining robustness gaps in:

- live runtime rebuild compatibility,
- the `agent-worker` behavioral contract,
- runtime state truthfulness,
- and registry/operator hygiene.

Each step below includes a strict **Definition of Done (DoD)** and a concrete **verification method**.

---

## Step 1 — Stabilize the live runtime rebuild path

### Step 1 goal

Make the source-repo runtime rebuild reliably, not just fresh throwaway installs.

### Step 1 findings addressed

- repo-root `agent-worker` restart loop caused by missing import dependencies
- repo-root `offline-docs-mcp` restart loop caused by MCP/FastMCP import mismatch
- lack of proof that an already-used local runtime converges after rebuild

### Step 1 changes

1. Audit startup-time imports for required runtime services, especially:
   - `agent-worker`
   - `offline-docs-mcp`
2. Ensure each required image installs every dependency needed at module import time.
3. Align `offline-docs` server code with the pinned MCP package/API shape actually installed in its image.
4. Rebuild the source-repo runtime from current HEAD and verify that required services converge healthy.
5. Add validation coverage for the source-repo runtime rebuild path, not only throwaway targets.

### Step 1 Definition of Done

- `scripts/factory_stack.py start --build` succeeds for the source repo runtime.
- Required runtime services no longer restart-loop after rebuild.
- `scripts/verify_factory_install.py --target .. --runtime --check-vscode-mcp` passes for the source-repo runtime where applicable.
- Required service logs contain no startup import errors.

### Step 1 verification

- rebuild the source-repo runtime with `scripts/factory_stack.py start --build`
- run runtime compliance verification against the source repo runtime
- inspect `docker ps` and service logs for restart loops or import failures

---

## Step 2 — Define the `agent-worker` contract explicitly

### Step 2 goal

Remove ambiguity about whether `agent-worker` is a real worker or a liveness placeholder.

### Step 2 findings addressed

- current `run-queue` mode is only a sleep loop
- current tests validate entrypoint wiring and healthcheck text, not real work execution

### Step 2 changes

Pick one explicit contract and align code, docs, and tests with it.

#### Option A — Placeholder contract

1. Document `agent-worker` as a compatibility/liveness stub only.
2. Ensure verification and docs do not imply real queue processing.
3. Keep health checks focused on liveness, not job execution.

#### Option B — Real worker contract

1. Define the queue/job source explicitly.
2. Implement polling and deterministic work execution.
3. Persist observable state transitions/results.
4. Add end-to-end test coverage proving a queued item is processed.

### Step 2 Definition of Done

#### If Option A

- docs describe `agent-worker` as a placeholder/liveness process only.
- tests validate only placeholder expectations.
- runtime verification language no longer implies active queue consumption.

#### If Option B

- `run-queue` performs real deterministic work from a defined source.
- at least one integration test proves a queued item is consumed and updates observable state.
- health checks reflect meaningful readiness, not just argument-string presence.

### Step 2 verification

- review docs + tests for contract consistency
- if Option B is chosen, run the worker integration test and inspect bus/state changes

---

## Step 3 — Make runtime state reporting truthful

### Step 3 goal

Ensure reported runtime state reflects actual Docker/runtime health rather than command-flow intent.

### Step 3 findings addressed

- `status` can report `starting` even when services are stuck restarting
- registry/runtime state can mislead operators during partial failure

### Step 3 changes

1. Define clearer runtime states, for example:
   - `installed`
   - `starting`
   - `running`
   - `degraded`
   - `failed`
   - `stopped`
2. Update lifecycle transitions to reflect observed runtime outcomes.
3. Detect restart loops, unhealthy required services, or partial startup failures.
4. Make `status` surface the truth from Docker/runtime inspection rather than only cached registry state.

### Step 3 Definition of Done

- `status` distinguishes healthy from degraded/failed stacks.
- partial startup failures do not leave misleading steady-state metadata.
- registry state after failed startup is reproducible and accurate.
- at least one automated test covers degraded-state reporting.

### Step 3 verification

- induce or simulate a partial startup failure
- run `scripts/factory_stack.py status`
- confirm registry state and observed Docker state agree

---

## Step 4 — Reduce registry noise from ephemeral workspaces

### Step 4 goal

Keep operator state readable and prevent repeated validation/test runs from polluting the workspace registry.

### Step 4 findings addressed

- `list` output accumulates many stale or throwaway records
- registry churn increases operator noise and obscures active workspaces

### Step 4 changes

1. Define what counts as ephemeral/test-generated workspace state.
2. Auto-prune ephemeral records more aggressively.
3. Consider tagging ephemeral records in registry metadata.
4. Reduce long-lived persistence of temporary validation/test workspaces where possible.
5. Keep `factory_stack.py list` operator-focused and readable.

### Step 4 Definition of Done

- repeated validation/test runs do not leave excessive long-lived registry clutter.
- `scripts/factory_stack.py list` remains readable after normal local test activity.
- ephemeral records are auto-pruned or clearly labeled.

### Step 4 verification

- run repeated throwaway validations
- inspect registry contents and `list` output
- confirm cleanup behavior stays bounded and predictable

---

## Step 5 — Final confidence pass

### Step 5 goal

Prove the mitigation is robust for both clean-room installs and the live source-repo runtime.

### Step 5 required validations

1. Quality gate:
   - `black --check factory_runtime/ scripts/ tests/`
   - `isort --check-only factory_runtime/ scripts/ tests/`
   - `flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841`
2. Contract/unit suites:
   - `pytest tests/test_factory_install.py -v`
   - `pytest tests/test_regression.py -v`
   - `pytest tests/test_multi_tenant.py -v`
3. Docker throwaway runtime regression:
   - `RUN_DOCKER_E2E=1 pytest tests/test_throwaway_runtime_docker.py -v -s`
4. Source-repo runtime rebuild validation:
   - rebuild current runtime
   - verify runtime compliance
   - inspect service health and logs

### Step 5 Definition of Done

- all required tests pass.
- Docker throwaway E2E passes.
- source-repo runtime rebuild is healthy.
- no required service restart-loops remain.
- the review can honestly conclude that the mitigation is implemented and still works under both fresh-install and live-runtime conditions.

---

## Recommended execution order

To reduce risk and keep history clean, execute the work in this order:

1. **Fix live runtime rebuild compatibility**
2. **Define the `agent-worker` contract**
3. **Make runtime state reporting truthful**
4. **Reduce registry noise**
5. **Run the full confidence pass**

This order addresses the strongest contradiction to “still works” first, then resolves contract ambiguity, then improves operator truthfulness and hygiene.
