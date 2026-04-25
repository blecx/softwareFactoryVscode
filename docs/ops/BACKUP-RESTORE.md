# Backup and Restore

## Supported today

The current supported runtime backup command is:

`./.venv/bin/python ./scripts/factory_stack.py backup`

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

## Restore status

Restore automation is **not** supported yet in this slice.

That work remains separate because the repository still needs:

- deterministic restore validation
- recovery-path safety checks
- roundtrip recovery proof

Until restore lands, this document defines only the supported backup contract and the expected bundle shape for future recovery work.
