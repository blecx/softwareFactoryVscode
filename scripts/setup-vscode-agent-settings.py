#!/usr/bin/env python3
"""Configure explicit VS Code agent settings from canonical .copilot config."""

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).parent.resolve()))
import factory_workspace  # noqa: E402

SCRIPT_DIR = Path(__file__).parent.resolve()
REPO_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = REPO_ROOT / ".copilot/config/vscode-agent-settings.json"
WORKSPACE_SETTINGS_PATH = REPO_ROOT / ".vscode/settings.json"

MANAGED_PREFIXES = (
    "chat.",
    "mcp.",
    "mcp",
    "github.copilot.",
    "issueagent.",
)

# Keys managed by other scripts (like setup-vscode-autoapprove.py)
IGNORED_KEYS = {
    "chat.tools.subagent.autoApprove",
    "chat.tools.terminal.autoApprove",
}


def is_managed_key(key: str) -> bool:
    if key in IGNORED_KEYS:
        return False
    return any(key == prefix or key.startswith(prefix) for prefix in MANAGED_PREFIXES)


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def reconcile_settings(
    existing: Dict[str, Any], new: Dict[str, Any]
) -> tuple[Dict[str, Any], list[str]]:
    """Reconciles owned keys completely from canonical config, returning updated dict and list of removed keys."""
    result = {}
    removed_keys = []

    # Preserve non-managed or explicitly ignored keys
    for key, value in existing.items():
        if not is_managed_key(key):
            result[key] = copy.deepcopy(value)
        elif key not in new:
            removed_keys.append(key)

    # Insert or update managed keys from canonical config
    for key, value in new.items():
        result[key] = copy.deepcopy(value)

    return result, removed_keys


def collect_drift(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Check for missing, mismatch, and extra keys in fully managed blocks."""
    drifts: list[str] = []

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            drifts.append(
                f"{path or '<root>'}: expected object, found {type(actual).__name__}"
            )
            return drifts

        for key, value in expected.items():
            child_path = f"{path}.{key}" if path else key
            if key not in actual:
                drifts.append(f"{child_path}: missing")
                continue
            drifts.extend(collect_drift(value, actual[key], child_path))

        # Check for extra keys in actual
        for key in actual:
            child_path = f"{path}.{key}" if path else key
            if not path:
                # At root level, only consider it drift if it's a managed key prefix and not in expected
                if is_managed_key(key) and key not in expected:
                    drifts.append(f"{child_path}: extra managed key (stale)")
            else:
                # Inside an owned root, any extra key is drift
                if key not in expected:
                    drifts.append(f"{child_path}: extra managed key")

        return drifts

    if expected != actual:
        drifts.append(f"{path}: expected={expected!r} actual={actual!r} (mismatched)")
    return drifts


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure or verify explicit VS Code agent settings."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check for drift without modifying files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    env_path = REPO_ROOT / ".factory.env"
    if not env_path.exists() and (REPO_ROOT.parent / ".factory.env").exists():
        env_path = REPO_ROOT.parent / ".factory.env"

    env_values = factory_workspace.parse_env_file(env_path)
    ports = {}
    for key in factory_workspace.PORT_LAYOUT:
        val = env_values.get(key)
        if val:
            try:
                ports[key] = int(val)
            except ValueError:
                pass
        if key not in ports:
            ports[key] = factory_workspace.PORT_LAYOUT[key]

    expected = factory_workspace.build_effective_workspace_settings(REPO_ROOT, ports)
    existing = load_json(WORKSPACE_SETTINGS_PATH)

    if args.check:
        drifts = collect_drift(expected, existing)
        if not drifts:
            print("✅ Workspace agent settings match canonical .copilot config")
            return 0
        print("❌ Workspace agent settings drift detected:")
        for drift in drifts[:20]:
            print(f"  - {drift}")
        if len(drifts) > 20:
            print(f"  - ... and {len(drifts) - 20} more")
        return 1

    updated, removed_keys = reconcile_settings(existing, expected)

    if args.dry_run:
        print("🔍 Dry Run: Previewing settings projection...")
        drifts = collect_drift(expected, existing)
        if not drifts and not removed_keys:
            print("✅ No changes needed. Settings are fully reconciled.")
        else:
            if removed_keys:
                print(f"🗑️  Would remove stale managed keys: {', '.join(removed_keys)}")
            if drifts:
                print("📝 Would reconcile the following drift:")
                for drift in drifts:
                    print(f"  - {drift}")
        return 0

    if removed_keys:
        print(f"🧹 Removed stale managed keys: {', '.join(removed_keys)}")

    write_json(WORKSPACE_SETTINGS_PATH, updated)
    print("✅ Workspace agent settings projected from .copilot config")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
