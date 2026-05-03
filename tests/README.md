# Software Factory Integration & Regression Tests

## `run-integration-test.sh`

This script serves as a **functional regression test** for the Software Factory. It validates the core architectural constraints of this repository when used as an isolated subsystem in a parent host project.

The script now stages its mock host under the repository-local, gitignored `.tmp/integration-test/` area and cleans it up on exit, keeping the regression inside the workspace guardrail by default.

### What it tests (regression coverage)

1. **Host Isolation (No Pollution):** Ensures the factory does not leak artifacts (like `.tmp` directories or `agent_metrics.json`) into the host project's root folder.
2. **Mount Safety:** Verifies `docker-compose` settings correctly map the target environments without accidentally over-mounting or missing the `.:/target` boundary.
3. **Internal Module Resolution:** Checks that internal python scripts remain properly namespace-scoped (`factory_runtime.agents`) and haven't regressed back to conflicting absolute imports (`from agents.`).

## Python test environment

This repository's supported contributor environment is `.venv` at the repo root.
Bootstrap it with:

```bash
./setup.sh
```

That installs:

- runtime dependencies from `factory_runtime/agents/requirements.txt`
- development and test tooling from `requirements.dev.txt`

If `./.venv/bin/python -m pytest` or `./.venv/bin/python -m black` fails with
`No module named ...`, the repo `.venv` is missing the development/test tooling
from `requirements.dev.txt`. Re-run `./setup.sh` to repair the environment
before retrying local checks. The local CI-parity precheck performs a Python
environment preflight and points back to the same repair path.

Run the installer regression suite with the supported environment:

```bash
./.venv/bin/pytest tests/test_factory_install.py -q
```

The throwaway-target regression in `tests/test_factory_install.py` validates the real install flow into a fresh git repository, including:

- namespaced harness install into `.copilot/softwareFactoryVscode/`
- host bootstrap artifacts
- Option B workspace generation
- post-install verifier success
- non-mutating smoke prompt output contract

## Fast-fail guardrail for CI-sensitive tests

When you add or change a CI-sensitive test, parity wrapper, or validation helper,
prefer **fast-fail** behavior over broad error aggregation.

- Stop on the **first blocking error** instead of continuing through later steps.
- Exit non-zero immediately and print the exact failing command and cause.
- Treat watchdogs/timeouts as a **hang fallback**, not the primary way users learn
  that a normal validation step failed.
- If diagnosis still needs replay support, expose focused rerun commands or named
  bundles instead of forcing one monolithic validation pass.

In short: normal failures should terminate with actionable output quickly, while
timeouts remain reserved for genuine stuck-process protection.

## Formatter guardrail for generated Python files

When a tool, agent, or repository-owned writer surface creates or rewrites
Python source, run **Black itself** before treating the save as complete.

- Use the actual formatter (`./.venv/bin/python -m black …` or the Black
  library), not a hand-formatted approximation.
- LF-only line endings and a trailing newline are necessary, but they are **not**
  a substitute for Black.
- If a writer path persists `.py` or `.pyi` files for issue resolution, it
  should apply Black-compatible formatting at save time so later
  `black --check` failures point to real drift rather than an avoidable write bug.

### Audited workflow-owned Python writer surfaces

The following surfaces have been audited and confirmed to call
`normalize_repo_text_for_write(..., require_python_formatter=True)` before
persisting Python files:

| Surface | Location | Audit status |
|---------|----------|-------------|
| `CoderAgent._implement` (primary issue-execution write path) | `factory_runtime/agents/coder_agent.py` | ✅ confirmed |
| `CoderAgent._validate_with_retry` (retry/repair write path) | `factory_runtime/agents/coder_agent.py` | ✅ confirmed |
| `write_file_content_typed` (filesystem tools) | `factory_runtime/agents/tooling/filesystem_tools.py` | ✅ confirmed |
| `FilesystemService.write_text` (repo-fundamentals MCP) | `factory_runtime/apps/mcp/repo_fundamentals/filesystem_service.py` | ✅ confirmed |

Regression locks for the `coder_agent` write paths are in
`tests/test_text_write_normalization.py` (structural AST-based audit tests).
End-to-end formatter fidelity for the filesystem-tool and filesystem-service
surfaces is covered by the existing `write_file_content_typed` and
`FilesystemService.write_text` functional tests in the same file.

## Practical baseline coverage map (P0/P1/P2 lock)

The practical per-workspace baseline is protected by a mix of functional and documentation regressions:

- **Install/update contract:** `tests/test_factory_install.py`
- **Lifecycle/activation/verification guidance drift:** `tests/test_regression.py`
- **Tenant-partitioned shared-service persistence/audit contract:** `tests/test_multi_tenant.py`
- **Host-isolation boundaries and subsystem mount safety:** `tests/run-integration-test.sh`
- **Todo-app throwaway regression contract:** `.copilot/skills/todo-app-regression/SKILL.md`, `scripts/todo_app_regression.py`, and `tests/test_todo_regression_contract.py`

The baseline intentionally distinguishes the default practical per-workspace
support path from the now-fulfilled ADR-008 shared multi-tenant promotion for
`mcp-memory`, `mcp-agent-bus`, and `approval-gate`.

Fulfilled ADR-008 promotion evidence beyond that baseline is covered by the
service-boundary isolation assertions in `tests/test_multi_tenant.py`, the
operator/runtime wording locks in `tests/test_regression.py`, and the optional
Docker-backed strict-tenant scenario in `tests/test_throwaway_runtime_docker.py`.

## Lifecycle proof matrix (practical baseline)

The current practical baseline is backed by an explicit mix of focused local
tests and opt-in Docker-backed proofs:

| Lifecycle path                     | Focused automated proof                                                                                                                               | Docker-backed evidence                                                                                                | Guarantee / note                                                                                                                                       |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A → B → A activation / switch-back | `test_activate_workspace_switch_back_clears_stale_selection_leases` in `tests/test_factory_install.py`                                                | `test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace` in `tests/test_throwaway_runtime_docker.py`  | Active selection, generated endpoints, and lease cleanup follow the operator-selected workspace rather than whichever runtime happened to start first. |
| Stop → status                      | `test_factory_stack_stop_followed_by_status_reports_needs_ramp_up` in `tests/test_factory_install.py`                                                 | `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart` in `tests/test_throwaway_runtime_docker.py` | After an explicit stop, manager-backed status reports `stopped` / `needs-ramp-up` instead of inventing a second runtime truth.                         |
| Stop → verify                      | `test_verify_factory_runtime_reports_needs_ramp_up_after_stop` in `tests/test_factory_install.py`                                                     | Reuses the same Docker stop proof above when real container teardown matters.                                         | Runtime verification fails closed with `needs-ramp-up` after a supported stop path.                                                                    |
| Cleanup / `runtime-deleted`        | `test_cleanup_workspace` and `test_delete_runtime_matches_cleanup_artifact_effects_with_distinct_trigger_metadata` in `tests/test_factory_install.py` | `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart` in `tests/test_throwaway_runtime_docker.py` | Cleanup and policy-driven `delete-runtime` remove live runtime ownership/artifacts while retaining the installed baseline and Docker images.           |
| Reload / reopen recovery           | `test_build_runtime_config_preserves_persisted_ports_when_workspace_reopens` in `tests/test_factory_install.py`                                       | Not required for the practical baseline; this is metadata/config recovery rather than live container truth.           | Reopening a workspace preserves the persisted port/runtime contract without implying hidden auto-start behavior.                                       |

The canonical production-grade parity command
`./.venv/bin/python ./scripts/local_ci_parity.py --mode production` now runs a
promoted blocking subset of these Docker-backed lifecycle proofs:

- `test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks`
- `test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart`
- `test_throwaway_runtime_backup_restore_roundtrip_recovers_state_and_runtime_contract`

Other Docker-backed lifecycle proofs remain **targeted and opt-in** via
`RUN_DOCKER_E2E=1`; they are required evidence where real container/image state
matters, but they are not silently upgraded into the default local-CI-parity
gate unless that policy is explicitly documented and reviewed.

## Readiness closeout evidence bundle

The reproducible evidence bundle for the current MCP harness readiness baseline
is:

```bash
./.venv/bin/pytest tests/test_regression.py -v
./.venv/bin/python ./scripts/local_ci_parity.py
./.venv/bin/python ./scripts/local_ci_parity.py --mode production
RUN_DOCKER_E2E=1 ./.venv/bin/pytest tests/test_throwaway_runtime_docker.py -k "activate_switch_back_keeps_one_active_workspace" -v
```

`./.venv/bin/python ./scripts/local_ci_parity.py --mode production` now covers
the promoted strict-tenant, stop/cleanup, and backup/restore Docker E2E scenarios.
Use the extra `RUN_DOCKER_E2E=1` command when the claim also depends on the
multi-workspace activation / switch-back proof.

The same canonical production gate also refreshes `.tmp/production-readiness/latest.md`,
`.tmp/production-readiness/latest.json`, and `.tmp/production-readiness/history.json`
for concise sign-off evidence and three-run streak tracking.

Still deferred after this readiness pass:

- dynamic profile expansion during a running prompt
- image pull/upgrade policy automation
- broader orchestration/event/UI work beyond the accepted ADR baseline
- blanket claims that every service is globally shared by default

Default throwaway install/runtime validation should stay inside the source repository's gitignored `.tmp/` tree (for example `.tmp/throwaway-targets/`) unless a test explicitly opts into an external target. This keeps disposable targets in-workspace and avoids accidentally tainting unrelated repositories or non-repository paths.

---

## Fresh Session Handoff Prompt

If you are starting a new AI coding session (e.g., via Copilot or another Agent), copy and paste the following prompt to safely initialize the workspace context:

> "Please review the `.copilot/softwareFactoryVscode/tests/run-integration-test.sh` script to understand the expected system bounds for this project. My goal is to use this Software Factory as a completely isolated toolchain inside my main development repository.
>
> 1. First, verify that `run-integration-test.sh` still passes.
> 2. Second, start reviewing the imported code in `scripts/` side-by-side with the workspace structure (`.code-workspace.template`) and `compose/docker-compose*.yml` files.
> 3. Third, if everything works and looks correct, write a brief README section advising the host project on how to start their first task via the Factory workspace.
>
> Do not modify the VS Code or Docker configurations unless the integration test explicitly fails or points to an issue."
