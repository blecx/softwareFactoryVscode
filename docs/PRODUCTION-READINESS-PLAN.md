# Internal Production Readiness Plan

This plan defines the work required to make `softwareFactoryVscode` production ready for **internal, self-hosted use**.

It is designed to be detailed enough to split directly into GitHub issues and execute without inventing missing scope later.

`docs/PRODUCTION-READINESS.md` is the canonical operator-facing readiness contract.
This plan remains the implementation roadmap for reaching that contract.

## Scope boundary

### In scope

- internal team-operated production use
- self-hosted deployment and runtime operations
- real secrets and non-mock service configuration
- repeatable validation, recovery, and operator workflows
- production readiness for the current namespace-first harness and manager-backed runtime model

### Explicitly out of scope

- external hosted multi-tenant SaaS production
- internet-facing customer tenancy and hosting guarantees
- SaaS-grade availability targets, billing, or customer-facing auth boundaries
- production claims for runtime features that are still explicitly deferred in architecture and implementation plans

This boundary is intentional. The repository should only claim production readiness for the operator model it actually supports.

## Production-ready exit definition

The project is production ready for internal use only when all of the following are true:

1. Docker build parity is part of a blocking production gate.
2. At least one repeatable Docker E2E runtime proof is part of a blocking production gate.
3. Non-mock runtime configuration and secrets fail closed.
4. Stateful runtime data can be backed up and restored through supported commands.
5. Operators have machine-readable runtime diagnostics and documented incident response.
6. One canonical production-readiness gate reports pass/fail from the manager-backed runtime truth.
7. The production-readiness gate passes locally, in CI, and in three consecutive clean runs.

## Existing baseline this plan builds on

The current repository already has a strong readiness baseline:

- `scripts/local_ci_parity.py` provides repo parity checks, but Docker builds are optional.
- `tests/test_throwaway_runtime_docker.py` provides real Docker-backed runtime proofs, but they are opt-in.
- `scripts/factory_stack.py` exposes the canonical lifecycle and status/preflight surfaces.
- `scripts/verify_factory_install.py` provides installation and runtime compliance checks.
- `factory_runtime/mcp_runtime/manager.py` and `factory_runtime/mcp_runtime/catalog.py` already define the authoritative runtime/readiness contract.
- Stateful runtime data already lives in known paths derived from `FACTORY_DATA_DIR`.

This plan must harden those surfaces, not replace them with parallel tooling.

## Workstreams

Each workstream below is written so it can become one GitHub issue or one small issue stack.

---

## PR-01 — Define the production-readiness contract

### PR-01 why

The repository needs one operator-facing definition of what “production ready” means for this project.

### PR-01 scope

Create one authoritative document describing:

- the target deployment model
- supported production scope
- explicit non-goals
- required validation gates
- required backup and recovery expectations
- required monitoring and incident-response expectations
- sign-off rules for calling the repo production ready

### PR-01 likely files

- `docs/PRODUCTION-READINESS.md` or fold this plan into a canonical production-readiness doc
- `docs/INSTALL.md`
- `docs/CHEAT_SHEET.md`
- `docs/HANDOUT.md`
- `README.md`

### PR-01 acceptance criteria

- one doc is clearly the source of truth for production readiness
- the doc explicitly states that external hosted multi-tenant SaaS production is out of scope
- the doc points to the canonical validation and runtime surfaces
- operator-facing docs use the same production-readiness wording

### PR-01 validation

- doc review against `ADR-012`, `ADR-008`, and `ADR-014`
- ensure no doc claims broader production scope than the runtime actually supports

### PR-01 dependencies

- none

### PR-01 suggested labels

- `production-readiness`
- `documentation`
- `runtime`

---

## PR-02 — Add an explicit production runtime/profile mode

### PR-02 why

The repo currently includes development-friendly behavior such as mock LLM fallback. Internal production readiness requires a distinct fail-closed production mode.

### PR-02 scope

Add an explicit runtime or validation profile that distinguishes development from production.

Production mode must:

- disable silent fallback to mock behavior
- require live configuration where needed
- surface its mode in preflight/status/readiness output
- fail closed when required live configuration is missing

### PR-02 likely files

- `compose/docker-compose.factory.yml`
- `factory_runtime/mcp_runtime/catalog.py`
- `factory_runtime/mcp_runtime/manager.py`
- `scripts/factory_stack.py`
- `scripts/verify_factory_install.py`
- `tests/test_mcp_runtime_manager.py`
- `tests/test_factory_install.py`

### PR-02 acceptance criteria

- production mode is explicit and operator-visible
- production mode cannot silently use `mock-llm-gateway` as a live substitute
- development mode preserves the current deterministic developer workflow
- runtime verification surfaces the effective mode clearly

### PR-02 validation

- unit tests for profile selection and readiness outcomes
- runtime verification must fail when production mode is selected with missing live config
- runtime verification must pass with valid live config

### PR-02 dependencies

- PR-01

### PR-02 suggested labels

- `production-readiness`
- `runtime`
- `security`

---

## PR-03 — Harden secrets and live-config handling

### PR-03 why

The repository already uses real secret inputs, but the current story is too loose for a production claim.

### PR-03 secret-bearing inputs that must be covered

- `CONTEXT7_API_KEY`
- `GITHUB_TOKEN`
- `GH_TOKEN`
- `GITHUB_PAT`
- `LLM_CONFIG_PATH`
- `LLM_OVERRIDE_PATH`
- `GITHUB_OPS_ALLOWED_REPOS`
- optional `OPENAI_API_KEY` paths if image tooling is meant to remain supported in production mode

### PR-03 scope

Define and enforce a live-config contract that covers:

- approved secret sources
- placeholder detection
- missing-secret detection
- config-path validation
- secret redaction in logs and diagnostics
- production restrictions on dev-only override flows

### PR-03 likely files

- `factory_runtime/agents/llm_client.py`
- `factory_runtime/apps/mcp/agent_bus/mcp_server.py`
- `factory_runtime/apps/mcp/github_ops/audit_store.py`
- `compose/docker-compose.context7.yml`
- `compose/docker-compose.mcp-github-ops.yml`
- `scripts/verify_factory_install.py`
- `factory_runtime/mcp_runtime/catalog.py`
- `factory_runtime/mcp_runtime/manager.py`

### PR-03 acceptance criteria

- production mode fails on missing or placeholder secrets
- repo-tracked config files remain secret-free
- diagnostics redact secret values
- readiness reason codes distinguish missing config from missing secret
- production mode disables or tightly gates dynamic live-key injection and override behavior

### PR-03 validation

- tests for secret detection and redaction
- tests for missing-secret and missing-config readiness outcomes
- runtime verification with valid live config passes without mock fallback

### PR-03 dependencies

- PR-01
- closely coordinated with PR-02

### PR-03 suggested labels

- `production-readiness`
- `security`
- `runtime`

---

## PR-04 — Make Docker build parity a blocking production gate

### PR-04 why

`docker/*/Dockerfile` builds are currently optional in local parity. Production readiness requires them to be blocking.

### PR-04 scope

Extend `scripts/local_ci_parity.py` with a production-grade mode that includes Docker image builds by default and fails when a build fails.

### PR-04 likely files

- `scripts/local_ci_parity.py`
- `.github/workflows/ci.yml`
- `docs/PRODUCTION-READINESS.md`
- `docs/INSTALL.md`

### PR-04 acceptance criteria

- there is one canonical production parity command
- Docker build parity is blocking in that mode
- CI includes a matching production parity lane
- output clearly distinguishes blocking failures from warnings

### PR-04 validation

- clean local run
- CI run
- induced Dockerfile failure produces a clear blocking failure report

### PR-04 dependencies

- PR-01

### PR-04 suggested labels

- `production-readiness`
- `ci`
- `runtime`

---

## PR-05 — Promote repeatable Docker E2E runtime proof into a standard gate

### PR-05 why

The repo already has useful Docker E2E tests, but they are opt-in behind `RUN_DOCKER_E2E=1`. Production readiness needs at least one real-runtime proof in a standard gate.

### PR-05 scope

Promote a stable subset of `tests/test_throwaway_runtime_docker.py` into a production-readiness lane.

### PR-05 recommended blocking scenarios

Minimum required:

- `test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`
- `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`

Strongly recommended:

- `test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace`

### PR-05 likely files

- `tests/test_throwaway_runtime_docker.py`
- `.github/workflows/ci.yml`
- `scripts/local_ci_parity.py`
- `docs/PRODUCTION-READINESS.md`
- `docs/INSTALL.md`

### PR-05 acceptance criteria

- at least one Docker E2E scenario is a blocking production gate
- preferred: two or more scenarios are blocking
- the lane is documented, repeatable, and not dependent on manual handholding
- the selected lane passes three consecutive clean runs

### PR-05 validation

- three local green runs
- three CI green runs
- failure output is clear and actionable

### PR-05 dependencies

- PR-01
- PR-04 is strongly recommended before final sign-off

### PR-05 suggested labels

- `production-readiness`
- `ci`
- `runtime`
- `testing`

---

## PR-06 — Add a supported backup command for stateful runtime data

### PR-06 why

The runtime already persists state in stable locations, but there is no supported operator backup contract.

### PR-06 stateful data currently in scope

- `FACTORY_DATA_DIR/memory/<factory_instance_id>/memory.db`
- `FACTORY_DATA_DIR/bus/<factory_instance_id>/agent_bus.db`
- `.copilot/softwareFactoryVscode/.factory.env`
- `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- workspace registry data when needed for recovery

### PR-06 scope

Add one canonical backup flow that creates a timestamped, documented backup bundle with metadata and checksums.

The issue must explicitly define whether supported backups require:

- `suspend`, or
- `stop`

Do not leave backup safety ambiguous.

### PR-06 likely files

- `factory_runtime/mcp_runtime/manager.py`
- `scripts/factory_stack.py`
- `scripts/factory_workspace.py`
- `docs/ops/BACKUP-RESTORE.md`
- `tests/test_mcp_runtime_manager.py`
- integration or throwaway-runtime tests as needed

### PR-06 acceptance criteria

- one canonical backup command exists
- backup output includes state, metadata, and checksums
- docs define when backup is safe to run
- backups stay within approved temp/data boundaries

### PR-06 validation

- automated test for bundle content
- manual throwaway backup drill

### PR-06 dependencies

- PR-01

### PR-06 suggested labels

- `production-readiness`
- `backup`
- `runtime`

---

## PR-07 — Add restore workflow and disaster-recovery roundtrip proof

### PR-07 why

Backup is incomplete until restore is automated and proven.

### PR-07 scope

Add a supported restore flow that can:

- restore memory and bus databases
- restore required runtime metadata
- validate instance/path/port safety
- restart the runtime and verify healthy recovery

### PR-07 required recovery proof

The implementation must prove a roundtrip flow:

1. start runtime
2. write representative state
3. create backup
4. stop or clean up runtime
5. restore from backup
6. restart runtime
7. verify state and isolation behavior

### PR-07 likely files

- `factory_runtime/mcp_runtime/manager.py`
- `scripts/factory_stack.py`
- `docs/ops/BACKUP-RESTORE.md`
- `tests/test_throwaway_runtime_docker.py` or a dedicated restore test file

### PR-07 acceptance criteria

- one canonical restore command exists
- restore behavior is documented and deterministic
- the automated roundtrip recovery proof passes
- restored runtime passes runtime verification and MCP endpoint checks

### PR-07 validation

- backup/restore integration test
- manual recovery drill on throwaway runtime

### PR-07 dependencies

- PR-06

### PR-07 suggested labels

- `production-readiness`
- `backup`
- `runtime`
- `testing`

---

## PR-08 — Add machine-readable monitoring and diagnostics surfaces

### PR-08 why

Current observability is strong for human operators but not yet formal enough for production operations.

### PR-08 scope

Expose canonical machine-readable runtime diagnostics, preferably by extending existing lifecycle surfaces rather than inventing parallel tooling.

Recommended output surfaces:

- `factory_stack.py status --json`
- `factory_stack.py preflight --json`

Diagnostics must expose at least:

- runtime state
- per-service readiness/health
- reason codes
- topology mode
- tenant diagnostics
- active workspace identity
- config drift and missing-secret outcomes
- repair state where relevant

### PR-08 likely files

- `scripts/factory_stack.py`
- `factory_runtime/mcp_runtime/manager.py`
- `scripts/verify_factory_install.py`
- `docs/ops/MONITORING.md`
- `tests/test_mcp_runtime_manager.py`
- `tests/test_factory_install.py`

### PR-08 acceptance criteria

- operators can consume one machine-readable status surface
- diagnostics are derived from the manager-backed snapshot/readiness model
- alert-triggering conditions are visible without parsing human-only output

### PR-08 validation

- schema or snapshot tests for JSON output
- manual collection of a diagnostic bundle from a running runtime

### PR-08 dependencies

- PR-01
- benefits from PR-02 and PR-03

### PR-08 suggested labels

- `production-readiness`
- `monitoring`
- `runtime`

---

## PR-09 — Publish incident-response and day-two operator runbooks

### PR-09 why

Production readiness requires operator procedures, not just tooling.

### PR-09 scope

Create runbooks for:

- startup failure
- unhealthy service
- missing secret or config
- shared-mode or tenant-identity misconfiguration
- restart and cleanup flows
- backup and restore
- update/rollback failure
- evidence collection before escalation

### PR-09 likely files

- `docs/ops/INCIDENT-RESPONSE.md`
- `docs/ops/MONITORING.md`
- `docs/ops/BACKUP-RESTORE.md`
- `docs/CHEAT_SHEET.md`
- `docs/INSTALL.md`

### PR-09 acceptance criteria

- every alert condition from PR-08 maps to an operator action
- runbooks only use canonical commands and contracts
- a new operator can execute the documented recovery steps without tribal knowledge

### PR-09 validation

- tabletop drill checklist
- documented unhealthy-service drill
- documented backup/restore drill

### PR-09 dependencies

- PR-06
- PR-07
- PR-08

### PR-09 suggested labels

- `production-readiness`
- `ops`
- `documentation`

---

## PR-10 — Add one canonical production-readiness gate and sign-off report

### PR-10 why

The repository needs a single command and CI lane that says pass or fail for internal production readiness.

### PR-10 scope

Create a single production-readiness gate that aggregates:

- production profile enforcement
- blocking Docker build parity
- blocking Docker E2E proof
- runtime verification including MCP endpoint checks
- backup/restore proof
- presence of required runbooks and documentation

Prefer extending existing validation surfaces rather than creating a disconnected new tool.

### PR-10 likely files

- `scripts/local_ci_parity.py`
- possibly a dedicated aggregator script if necessary
- `.github/workflows/ci.yml`
- `docs/PRODUCTION-READINESS.md`
- task definitions if repo-managed

### PR-10 acceptance criteria

- one canonical production-readiness command exists
- one CI lane runs the same gate
- the gate fails on any missing blocker
- final sign-off requires three consecutive green runs

### PR-10 validation

- local clean run
- CI clean run
- repeated green runs without manual exceptions

### PR-10 dependencies

- PR-02 through PR-09

### PR-10 suggested labels

- `production-readiness`
- `ci`
- `runtime`
- `ops`

---

## Recommended execution order

### Phase 0 — Define target and rules

1. PR-01

### Phase 1 — Close the biggest production blockers

1. PR-02
2. PR-03
3. PR-04
4. PR-05

### Phase 2 — Make runtime state recoverable

1. PR-06
2. PR-07

### Phase 3 — Make operations real

1. PR-08
2. PR-09

### Phase 4 — Final sign-off

1. PR-10

## Critical path

The fastest route to internal production readiness is:

`PR-01 -> (PR-02 + PR-03 + PR-04 + PR-05) -> PR-06 -> PR-07 -> (PR-08 + PR-09) -> PR-10`

## Final sign-off checklist

The repository should not be called production ready for internal use until all of the following are true:

- [ ] production mode exists and is fail-closed
- [ ] mock fallback is disabled or blocked in production mode
- [ ] Docker build parity is blocking
- [ ] Docker E2E proof is blocking
- [ ] live secrets and config are validated and redacted
- [ ] supported backup flow exists
- [ ] supported restore flow exists and is proven
- [ ] machine-readable monitoring/diagnostics exist
- [ ] incident-response runbooks exist and have been exercised
- [ ] one canonical production-readiness gate exists
- [ ] the gate passes locally and in CI
- [ ] the gate has passed three consecutive times

## Notes for issue creation

When creating issues from this plan, use these common fields:

- include explicit dependencies between issues
- keep scope narrow enough that each issue can be validated independently
- use acceptance criteria and validation commands from this plan verbatim where possible
- apply labels such as `production-readiness`, `runtime`, `ci`, `security`, `ops`, `backup`, and `monitoring` as appropriate

This plan is complete enough to split into implementation issues without expanding the scope to external hosted multi-tenant SaaS production.
