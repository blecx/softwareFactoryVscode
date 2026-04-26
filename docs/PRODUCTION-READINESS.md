# Internal Production Readiness Contract

This document is the canonical operator-facing contract for when `softwareFactoryVscode` may be described as production ready.

`docs/PRODUCTION-READINESS-PLAN.md` is the implementation roadmap for reaching this contract. It is not the readiness authority by itself.

## Status

`softwareFactoryVscode` is **not** entitled to claim full internal production readiness merely because the current default branch ships a strong namespace-first baseline.

The repository may be described as production ready only after every blocking requirement in this contract is satisfied and the final sign-off evidence has been recorded.

## Supported production boundary

The supported production target is **internal, self-hosted production** for the current namespace-first harness and manager-backed runtime model.

That boundary assumes:

- the canonical installed runtime contract remains under `.copilot/softwareFactoryVscode/` per `ADR-012`;
- the supported operator entrypoint is the generated `software-factory.code-workspace` file;
- runtime truth comes from the manager-backed snapshot and readiness surfaces exposed through `scripts/factory_stack.py` and `scripts/verify_factory_install.py`;
- shared-capable services follow the deliberate, evidence-backed promotion rules from `ADR-008`; and
- production readiness claims stay aligned with the MCP runtime authority defined by `ADR-014`.

## Explicitly out of scope

The repository must **not** claim this contract covers:

- external hosted multi-tenant SaaS production;
- customer-facing internet-hosted tenancy, billing, or SaaS authentication boundaries;
- blanket claims that every MCP service is globally shared or that shared mode is the default operator path; or
- any second lifecycle, readiness, or runtime-truth authority outside the manager-backed contract.

## Normative readiness authorities

The following sources define the readiness boundary and must stay aligned:

- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/architecture/ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`
- `docs/architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`
- `scripts/factory_stack.py` for canonical lifecycle, `preflight`, and `status`
- `scripts/verify_factory_install.py` for installation/runtime verification
- `scripts/local_ci_parity.py` for both the repo's default CI-parity baseline and the canonical production-grade parity command
- `docs/PRODUCTION-READINESS-PLAN.md` for the bounded implementation roadmap

Operator-facing summaries in `README.md`, `docs/INSTALL.md`, `docs/CHEAT_SHEET.md`, and `docs/HANDOUT.md` must defer to this document rather than define a competing readiness story.

## Blocking requirements for an internal production claim

A final internal-production claim requires all of the following to be true:

1. An explicit internal-production runtime mode exists and fails closed on missing live configuration.
2. Production-required secrets and live config are validated, placeholders are rejected, and production mode does not silently downgrade to mock behavior.
3. Docker build parity is part of a blocking production gate.
4. At least one repeatable Docker E2E runtime proof is part of a blocking production gate.
5. Stateful runtime data can be backed up through a supported command with documented preconditions, metadata, and checksums.
6. Stateful runtime data can be restored through a supported workflow with a documented recovery roundtrip proof.
7. Operators have machine-readable runtime diagnostics derived from the manager-backed snapshot/readiness contract.
8. Incident-response and day-two operator runbooks exist for the supported internal runtime model.
9. One canonical internal production-readiness gate aggregates the blocking requirements above and reports a pass/fail result.

Until every blocking requirement exists and is validated, the repository must describe itself as having a readiness **baseline** or **plan**, not as fully production ready.

## Explicit runtime mode selector (current PR-02 contract)

The current explicit runtime mode selector is `FACTORY_RUNTIME_MODE`.

- `development` is the default and preserves the current deterministic local workflow, including mock-friendly behavior where the repository already supports it.
- `production` selects the manager-backed `workspace-production` runtime profile and must fail closed when required live configuration is missing.

The authoritative behavior of `FACTORY_RUNTIME_MODE=production` is:

- `scripts/factory_stack.py preflight` and `scripts/factory_stack.py status` surface the effective mode as `runtime_mode=production` through the manager-backed snapshot/readiness contract.
- `scripts/verify_factory_install.py --runtime` refuses to report a ready runtime when required live configuration for the production profile is missing.
- the production profile excludes `mock-llm-gateway` from default readiness and startup, so production mode cannot silently substitute the mock gateway for a live runtime dependency.
- production-mode GitHub Models usage requires a live GitHub credential (`GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_PAT`, or a non-placeholder configured API key); placeholder/mock fallback is disabled.
- production-mode image generation requires a live `OPENAI_API_KEY` when that tooling path is invoked; mock image fallback is disabled there as well.

The current production secret/config contract covered by the manager-backed readiness path is:

- `CONTEXT7_API_KEY` must be present and non-placeholder for the `context7` service.
- one live GitHub Models credential must be available for the agent-worker path via `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_PAT`, or a non-placeholder `api_key` resolved from `LLM_CONFIG_PATH`.
- `GITHUB_OPS_ALLOWED_REPOS` must contain real `owner/repo` entries for `github-ops-mcp`; placeholders such as `YOUR_ORG/YOUR_REPO` are rejected in production mode.
- `LLM_CONFIG_PATH`, when used for production credentials, must resolve to a readable JSON object rather than a missing or malformed file.
- `LLM_OVERRIDE_PATH` override files and dynamic live-key injection flows such as `bus_set_live_key` are development-only and blocked in production mode.
- touched audit and diagnostic surfaces must redact secret values rather than echoing them back in plain text.

When production validation fails, the readiness/verifier surfaces distinguish missing configuration (`missing-config`) from missing secret material (`missing-secret`) instead of collapsing both into a generic error.

This is a necessary blocking requirement for the internal production claim, not the final claim by itself.

## Supported backup and restore contract (current PR-06 / PR-07 contract)

The current supported recovery lifecycle commands are:

- `scripts/factory_stack.py backup`
- `scripts/factory_stack.py restore --bundle-path <bundle-dir>`
- `scripts/factory_stack.py resume`

- Supported backups require the manager-backed bounded `suspended` lifecycle state.
- Operators must suspend a ready runtime before backup; the canonical precondition step is `scripts/factory_stack.py suspend --completed-tool-call-boundary` when the session can prove a safe boundary.
- The backup command writes a timestamped bundle under `FACTORY_DATA_DIR/backups/<factory_instance_id>/backup-<timestamp>/`.
- Each supported bundle includes the stateful runtime databases, the canonical `.factory.env`, the current runtime manifest, a scoped workspace-registry snapshot, a manager-backed runtime snapshot, and a `checksums.sha256` file.
- The bundle manifest (`bundle-manifest.json`) records the required precondition, bundle timestamp, selected profiles, recovery classification, and per-artifact SHA-256 metadata.
- Supported restore automation accepts only bundles captured from a `resume-safe` bounded suspended state with `completed_tool_call_boundary=true`.
- Restore validates bundle checksums plus target identity/path/compose/port alignment before mutating the runtime contract.
- Restore rehydrates the supported memory/agent-bus data and regenerates the canonical `.factory.env`, runtime manifest, and registry record through the manager-backed artifact sync path.
- A successful restore leaves the runtime in the bounded `suspended` state, and the canonical next step is `scripts/factory_stack.py resume`.
- The repository includes a Docker-backed roundtrip recovery proof in `tests/test_throwaway_runtime_docker.py` that verifies backup → cleanup → restore → resume plus runtime verification.

This closes blocking requirement `6` for the supported internal runtime boundary, but it does **not** waive any of the other blocking requirements above.

## Supported machine-readable monitoring surface (current PR-08 contract)

The current canonical machine-readable monitoring surface is the additive JSON form of the existing lifecycle commands:

- `scripts/factory_stack.py preflight --json`
- `scripts/factory_stack.py status --json`

These commands remain grounded in the same authoritative manager-backed snapshot/readiness contract already used by the human-oriented lifecycle output.

The supported JSON surface includes:

- runtime state and lifecycle metadata;
- per-service health/status plus service-level reason codes/details where present;
- readiness status, recommended action, and top-level blocking reason codes;
- topology mode and shared-mode tenant diagnostics; and
- canonical workspace identity, including active-workspace facts.

Operator automation and alerting should consume this JSON surface instead of scraping prose. See `docs/ops/MONITORING.md` for the supported field layout and triage examples.

## Supported operator runbooks (current PR-09 contract)

Blocking requirement `8` is satisfied only by the current operator runbooks for the manager-backed runtime model:

- `docs/ops/INCIDENT-RESPONSE.md` for incident response, diagnosis/action/validation/escalation flows, and day-two recovery decisions;
- `docs/ops/MONITORING.md` for the machine-readable status/reason-code field layout; and
- `docs/ops/BACKUP-RESTORE.md` for the bounded backup/restore contract and roundtrip recovery flow.

These runbooks map the supported monitoring statuses and reason-code families to concrete operator actions without authorizing legacy flows or a second lifecycle authority.

## Current baseline: necessary, not sufficient

The current default branch already provides a meaningful readiness baseline:

- namespace-first install/update under `.copilot/softwareFactoryVscode/`;
- manager-backed lifecycle and readiness vocabulary through `preflight`, `status`, and runtime verification;
- the repo-wide CI-parity path `./.venv/bin/python ./scripts/local_ci_parity.py`; and
- targeted Docker-backed lifecycle proofs where real container/image truth matters.

That baseline is necessary for internal production readiness, but it is not sufficient by itself. It does not waive any blocking requirement listed above.

## Local parity surfaces: default baseline vs production gate

Use the local parity commands intentionally:

- `./.venv/bin/python ./scripts/local_ci_parity.py` is the default faster baseline for day-to-day local iteration. In this path, Docker image build parity remains an explicit warning-only skip so routine development does not silently become a slow production sign-off lane.
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production` is the canonical internal production-readiness gate. It includes `docker/*/Dockerfile` builds by default, runs the promoted Docker E2E runtime proof lane (including the backup/restore roundtrip), blocks on missing required internal-production docs/runbooks, and writes the latest concise sign-off bundle to `.tmp/production-readiness/latest.md` plus `.tmp/production-readiness/latest.json`.
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --production-group <docs-contract|docker-builds|runtime-proofs>` runs one named production-only diagnostic group at a time for targeted replay. These runs improve diagnosis but do **not** replace or refresh the canonical aggregate sign-off bundle.
- `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout` is the closest local replay of GitHub's checkout-and-bootstrap behavior. It creates a clean git worktree snapshot, runs `./setup.sh`, and then replays the canonical production gate there before you trust the result as merge-grade local evidence.
- `./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build` remains supported as a compatibility alias when you want the Docker build expansion path without switching the named mode, but it does **not** add the promoted Docker E2E lane and the canonical production sign-off command is `--mode production`.

The promoted blocking Docker E2E lane currently covers:

- `test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`
- `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`
- `test_throwaway_runtime_backup_restore_roundtrip_recovers_state_and_runtime_contract`

`test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace`
remains targeted supplemental evidence when a sign-off claim depends on
explicit multi-workspace activation truth beyond the promoted gate.

## Evidence and sign-off rules

Any final internal-production sign-off must be reproducible, bounded, and retained as evidence.

At minimum, the final evidence bundle must include:

- the repo CI-parity baseline via `./.venv/bin/python ./scripts/local_ci_parity.py`;
- the canonical blocking production parity command via `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`;
- the exact fresh-checkout replay path via `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout` whenever merge-grade confidence depends on GitHub-like checkout/bootstrap semantics;
- runtime verification against the generated effective endpoints and manager-backed readiness surface;
- the blocking Docker E2E runtime proof lane, currently satisfied by the promoted strict-tenant, stop/cleanup, and backup/restore roundtrip scenarios within `./.venv/bin/python ./scripts/local_ci_parity.py --mode production`;
- supported backup and restore evidence, including one recovery roundtrip proof;
- machine-readable diagnostics evidence for the supported lifecycle surface (for example `scripts/factory_stack.py status --json` or `scripts/factory_stack.py preflight --json`);
- links to the required runbooks and operator procedures; and
- the latest sign-off bundle emitted by the canonical gate at `.tmp/production-readiness/latest.md` and `.tmp/production-readiness/latest.json`; and
- the canonical internal production-readiness gate passing locally, in CI, and in **three consecutive clean runs**.

## Final sign-off rule

`softwareFactoryVscode` may be described as ready for **internal self-hosted production** only when all blocking requirements are implemented, the canonical internal production-readiness gate is green locally and in CI, and three consecutive clean runs have been recorded without waiving blockers.

Anything less than that is a baseline, an in-progress hardening state, or a roadmap milestone — not a final production claim.
