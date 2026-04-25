# Backup and Restore

For the incident-response decision tree that tells you when to suspend, backup, restore, resume, restart, or escalate, use [`INCIDENT-RESPONSE.md`](INCIDENT-RESPONSE.md).

## Supported today

The current supported runtime lifecycle commands are:

`./.venv/bin/python ./scripts/factory_stack.py backup`

`./.venv/bin/python ./scripts/factory_stack.py restore --bundle-path <bundle-dir>`

`./.venv/bin/python ./scripts/factory_stack.py resume`

## Required precondition

Supported backups require the manager-backed bounded `suspended` lifecycle state.

From a ready runtime, the canonical precondition flow is:

1. Suspend the runtime.
2. Prefer `--completed-tool-call-boundary` when the current session can prove it is paused after a completed tool call.
3. Run the backup command.

Example:

- `./.venv/bin/python ./scripts/factory_stack.py suspend --completed-tool-call-boundary`
- `./.venv/bin/python ./scripts/factory_stack.py backup`

If the runtime is not currently `suspended`, the backup command fails clearly and does not create a supported bundle.

## Bundle location

Backups are written inside the approved runtime data boundary:

`FACTORY_DATA_DIR/backups/<factory_instance_id>/backup-<timestamp>/`

This keeps the supported artifact inside the repo-managed runtime data namespace instead of creating a second backup authority elsewhere on the host.

## Bundle contents

Each supported bundle includes:

- `data/memory/<factory_instance_id>/memory.db`
- `data/bus/<factory_instance_id>/agent_bus.db`
- `workspace/.copilot/softwareFactoryVscode/.factory.env`
- `workspace/.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json`
- `metadata/runtime-snapshot.json`
- `metadata/workspace-registry.json`
- `checksums.sha256`
- `bundle-manifest.json`

## Bundle metadata

`bundle-manifest.json` records:

- bundle timestamp
- workspace and instance identity
- runtime mode and lifecycle state
- required precondition (`suspended`)
- selected runtime profiles
- recovery classification and completed-tool-call-boundary status
- per-artifact SHA-256 checksums and sizes

`checksums.sha256` provides a flat checksum list for the captured files.

## Supported restore contract

The supported restore entrypoint is:

`./.venv/bin/python ./scripts/factory_stack.py restore --bundle-path <bundle-dir>`

Restore is deterministic and fails closed unless all of the following are true before any runtime metadata is rewritten:

- the bundle manifest is schema-version `1`;
- the bundle was captured from the bounded `suspended` lifecycle state;
- the bundle recorded `recovery_classification=resume-safe` and `completed_tool_call_boundary=true`;
- the bundle checksums still match every captured artifact;
- the target workspace path, canonical factory path, workspace identity, compose project, and port block match the current installed workspace; and
- the backed-up port block is currently available and the target compose project is not still running.

The restore flow rehydrates only the supported runtime boundary:

- `data/memory/<factory_instance_id>/memory.db`
- `data/bus/<factory_instance_id>/agent_bus.db`
- the canonical `.factory.env`
- the canonical runtime manifest and registry record via the manager-backed runtime artifact sync path

Restore does **not** auto-start the runtime. A successful restore leaves the runtime in the bounded `suspended` state so the canonical next step is `resume`.

## Canonical roundtrip recovery flow

Use this bounded recovery sequence for the supported disaster-recovery roundtrip:

1. `./.venv/bin/python ./scripts/factory_stack.py suspend --completed-tool-call-boundary`
2. `./.venv/bin/python ./scripts/factory_stack.py backup`
3. `./.venv/bin/python ./scripts/factory_stack.py cleanup` (or `stop --remove-volumes` when you are intentionally keeping metadata in place)
4. `./.venv/bin/python ./scripts/factory_stack.py restore --bundle-path <bundle-dir>`
5. `./.venv/bin/python ./scripts/factory_stack.py resume`
6. `./.venv/bin/python ./scripts/verify_factory_install.py --target . --runtime --check-vscode-mcp`

The Docker-backed roundtrip proof for this contract lives in `tests/test_throwaway_runtime_docker.py` and verifies that representative memory and agent-bus state survive cleanup, restore, resume, and runtime verification.
