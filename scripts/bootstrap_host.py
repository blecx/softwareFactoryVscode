#!/usr/bin/env python3
"""Bootstrap host-side files for a Software Factory installation."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import factory_release
import factory_workspace

FACTORY_DIRNAME = ".copilot/softwareFactoryVscode"
TMP_SUBPATH = Path(FACTORY_DIRNAME) / ".tmp"
DEFAULT_WORKSPACE_FILENAME = "software-factory.code-workspace"
DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"
WORKSPACE_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent / "workspace.code-workspace.template"
)
GITIGNORE_BLOCK = [
    "# Factory Isolation",
    f"{FACTORY_DIRNAME}/.tmp/",
    f"{FACTORY_DIRNAME}/.factory.env",
]
LEGACY_GITIGNORE_HEADER = "# Hidden-tree softwareFactoryVscode install artifacts"
LEGACY_GITIGNORE_BLOCK = [
    LEGACY_GITIGNORE_HEADER,
    ".softwareFactoryVscode/",
    ".factory.env",
    ".factory.lock.json",
    ".tmp/",
]


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)
        handle.write("\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a target repository for Software Factory."
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target repository root (default: current directory)",
    )
    parser.add_argument(
        "--workspace-file",
        default=DEFAULT_WORKSPACE_FILENAME,
        help=(
            "Workspace filename to generate in the target repository "
            f"(default: {DEFAULT_WORKSPACE_FILENAME})"
        ),
    )
    parser.add_argument(
        "--skip-workspace",
        action="store_true",
        help="Do not generate the host-facing VS Code workspace file.",
    )
    parser.add_argument(
        "--force-workspace",
        action="store_true",
        help="Overwrite an existing workspace file if it differs from the generated one.",
    )
    parser.add_argument(
        "--skip-gitignore",
        action="store_true",
        help="Do not add factory runtime artifacts to the target repository .gitignore.",
    )
    parser.add_argument(
        "--factory-version",
        default="",
        help="Human-readable factory version or ref label to record in .copilot/softwareFactoryVscode/lock.json.",
    )
    parser.add_argument(
        "--factory-commit",
        default="",
        help="Resolved git commit SHA to record in .copilot/softwareFactoryVscode/lock.json.",
    )
    parser.add_argument(
        "--repo-url",
        default="",
        help="Canonical source repository URL to record in .copilot/softwareFactoryVscode/lock.json.",
    )
    return parser.parse_args(argv)


def resolve_target_dir(target: str) -> Path:
    return Path(target).expanduser().resolve()


def ensure_factory_present(target_dir: Path) -> Path:
    factory_dir = target_dir / FACTORY_DIRNAME
    if not factory_dir.exists():
        raise FileNotFoundError(
            "Factory directory not found. Please run install_factory.py first."
        )
    return factory_dir


def ensure_tmp_dir(target_dir: Path) -> Path:
    tmp_dir = target_dir / TMP_SUBPATH
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Required runtime data directories for MCP services ensuring Docker doesn't map them with root ownership
    for sub in [
        "agent-script-runs",
        "mcp-docker-compose",
        "mcp-test-runner",
        "mcp-github-ops",
        "mcp-offline-docs",
    ]:
        (tmp_dir / sub).mkdir(parents=True, exist_ok=True)

    return tmp_dir


def sync_factory_runtime_contract(
    target_dir: Path,
    *,
    workspace_file: str,
) -> tuple[factory_workspace.WorkspaceRuntimeConfig, bool]:
    factory_dir = ensure_factory_present(target_dir)
    env_path = target_dir / FACTORY_DIRNAME / ".factory.env"
    existed_before = env_path.exists()
    config = factory_workspace.build_runtime_config(
        target_dir,
        factory_dir=factory_dir,
        workspace_file=workspace_file,
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
        write_env=True,
    )
    return config, not existed_before


def ensure_gitignore_entries(target_dir: Path) -> tuple[Path, bool]:
    gitignore_path = target_dir / ".gitignore"
    existing_text = (
        gitignore_path.read_text(encoding="utf-8") if gitignore_path.exists() else ""
    )
    existing_lines = existing_text.splitlines()
    normalized_lines, removed_legacy = strip_legacy_gitignore_entries(existing_lines)
    missing_lines = [line for line in GITIGNORE_BLOCK if line not in normalized_lines]

    if not missing_lines and not removed_legacy:
        return gitignore_path, False

    updated_text = "\n".join(normalized_lines)
    if updated_text and not updated_text.endswith("\n"):
        updated_text += "\n"
    if updated_text and (missing_lines or removed_legacy):
        updated_text += "\n"
    updated_text += "\n".join(missing_lines) + "\n"
    gitignore_path.write_text(updated_text, encoding="utf-8")
    return gitignore_path, True


def strip_legacy_gitignore_entries(existing_lines: list[str]) -> tuple[list[str], bool]:
    updated_lines: list[str] = []
    removed_legacy = False
    skip_legacy_block = False

    for line in existing_lines:
        stripped = line.strip()

        if stripped == LEGACY_GITIGNORE_HEADER:
            removed_legacy = True
            skip_legacy_block = True
            continue

        if skip_legacy_block and stripped in LEGACY_GITIGNORE_BLOCK[1:]:
            removed_legacy = True
            continue

        if skip_legacy_block and stripped == "":
            skip_legacy_block = False
            if updated_lines and updated_lines[-1] != "":
                updated_lines.append("")
            continue

        if skip_legacy_block:
            skip_legacy_block = False

        updated_lines.append(line)

    while updated_lines and updated_lines[-1] == "":
        updated_lines.pop()

    return updated_lines, removed_legacy


def find_legacy_gitignore_entries(existing_lines: list[str]) -> list[str]:
    findings: list[str] = []
    line_set = {line.strip() for line in existing_lines}
    for entry in LEGACY_GITIGNORE_BLOCK:
        if entry in line_set:
            findings.append(entry)
    return findings


def resolve_workspace_path(target_dir: Path, workspace_file: str) -> Path:
    candidate = Path(workspace_file).expanduser()
    if candidate.is_absolute():
        return candidate
    return target_dir / candidate


def deep_merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_workspace_folders(
    existing_folders: list[dict[str, Any]],
    desired_folders: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    desired_pairs = {
        (entry.get("name"), entry.get("path"))
        for entry in desired_folders
        if isinstance(entry, dict)
    }
    extras = [
        entry
        for entry in existing_folders
        if isinstance(entry, dict)
        and (entry.get("name"), entry.get("path")) not in desired_pairs
    ]
    return [*desired_folders, *extras]


def can_refresh_managed_workspace(current_data: dict[str, Any]) -> bool:
    allowed_top_level_keys = {"folders", "settings"}
    if any(key not in allowed_top_level_keys for key in current_data):
        return False

    folders = current_data.get("folders")
    if not isinstance(folders, list):
        return False

    current_pairs = {
        (entry.get("name"), entry.get("path"))
        for entry in folders
        if isinstance(entry, dict)
    }
    required_pairs = {
        ("Host Project (Root)", "."),
        ("AI Agent Factory", FACTORY_DIRNAME),
    }
    return required_pairs.issubset(current_pairs)


def merge_workspace_file_content(
    current_data: dict[str, Any], desired_data: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(current_data)
    merged["folders"] = merge_workspace_folders(
        current_data.get("folders", []),
        desired_data.get("folders", []),
    )

    current_settings = current_data.get("settings", {})
    desired_settings = desired_data.get("settings", {})
    if not isinstance(current_settings, dict):
        current_settings = {}
    if not isinstance(desired_settings, dict):
        desired_settings = {}
    merged["settings"] = deep_merge_dict(current_settings, desired_settings)
    return merged


def render_workspace_file(config: factory_workspace.WorkspaceRuntimeConfig) -> str:
    template = load_json(WORKSPACE_TEMPLATE_PATH)
    template["settings"] = config.workspace_settings
    return json.dumps(template, indent=2, ensure_ascii=False) + "\n"


def read_factory_head_commit(factory_dir: Path) -> str:
    if not (factory_dir / ".git").exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(factory_dir), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def read_factory_repo_url(factory_dir: Path) -> str:
    if not (factory_dir / ".git").exists():
        return ""
    try:
        result = subprocess.run(
            ["git", "-C", str(factory_dir), "remote", "get-url", "origin"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def resolve_lock_metadata(
    factory_dir: Path,
    *,
    requested_version: str,
    requested_commit: str,
    requested_repo_url: str,
    existing_lock: dict[str, Any],
) -> tuple[str, str, str]:
    existing_factory = existing_lock.get("factory", {})
    existing_factory = existing_factory if isinstance(existing_factory, dict) else {}

    version = requested_version.strip()
    if not version:
        version_file = factory_dir / "VERSION"
        if version_file.exists():
            version = version_file.read_text(encoding="utf-8").strip()
    if not version:
        version = str(existing_lock.get("version", "")).strip()
    if not version:
        version = "main"

    commit = requested_commit.strip() or read_factory_head_commit(factory_dir)
    if not commit:
        commit = str(existing_factory.get("commit", "")).strip()

    repo_url = requested_repo_url.strip() or read_factory_repo_url(factory_dir)
    if not repo_url:
        repo_url = str(existing_factory.get("repo_url", "")).strip()
    if not repo_url:
        repo_url = DEFAULT_REPO_URL

    return version, commit, repo_url


def ensure_workspace_file(
    target_dir: Path,
    workspace_file: str,
    config: factory_workspace.WorkspaceRuntimeConfig,
    *,
    force: bool = False,
) -> tuple[Path, str]:
    workspace_path = resolve_workspace_path(target_dir, workspace_file)
    desired = render_workspace_file(config)
    desired_data = json.loads(desired)
    existed_before = workspace_path.exists()

    if existed_before:
        current = workspace_path.read_text(encoding="utf-8")
        if current == desired:
            return workspace_path, "unchanged"
        if not force:
            try:
                current_data = json.loads(current)
            except json.JSONDecodeError:
                current_data = None

            if isinstance(current_data, dict) and can_refresh_managed_workspace(
                current_data
            ):
                merged_data = merge_workspace_file_content(current_data, desired_data)
                merged = json.dumps(merged_data, indent=2, ensure_ascii=False) + "\n"
                if merged != current:
                    workspace_path.write_text(merged, encoding="utf-8")
                    return workspace_path, "updated"
                return workspace_path, "unchanged"
        if not force:
            return workspace_path, "skipped-conflict"

    workspace_path.write_text(desired, encoding="utf-8")
    return workspace_path, "updated" if existed_before else "created"


def update_lock_file(
    target_dir: Path,
    *,
    factory_version: str,
    factory_commit: str,
    repo_url: str,
    workspace_file: str,
) -> Path:
    lock_path = target_dir / ".copilot/softwareFactoryVscode/lock.json"
    now = utc_now_iso()
    lock_data = load_json(lock_path)
    factory_dir = target_dir / FACTORY_DIRNAME
    resolved_version, resolved_commit, resolved_repo_url = resolve_lock_metadata(
        factory_dir,
        requested_version=factory_version,
        requested_commit=factory_commit,
        requested_repo_url=repo_url,
        existing_lock=lock_data,
    )
    installed_at = lock_data.get("installed_at", now)
    release_metadata = factory_release.build_lock_release_metadata(
        factory_dir,
        repo_url=resolved_repo_url,
        source_ref=factory_release.DEFAULT_BRANCH,
        version_core=resolved_version,
        commit_sha=resolved_commit,
    )
    lock_data.update(
        {
            "version": resolved_version,
            "installed_at": installed_at,
            "updated_at": now,
            "release": release_metadata,
            "factory": {
                "repo_url": resolved_repo_url,
                "install_path": FACTORY_DIRNAME,
                "workspace_file": workspace_file,
                "commit": resolved_commit,
            },
        }
    )
    write_json(lock_path, lock_data)
    return lock_path


def bootstrap_target(
    target_dir: Path,
    *,
    workspace_file: str,
    skip_workspace: bool,
    force_workspace: bool,
    skip_gitignore: bool,
    factory_version: str,
    factory_commit: str,
    repo_url: str,
) -> dict[str, Any]:
    ensure_factory_present(target_dir)
    tmp_dir = ensure_tmp_dir(target_dir)
    runtime_config, factory_env_created = sync_factory_runtime_contract(
        target_dir,
        workspace_file=workspace_file,
    )
    factory_env_path = target_dir / FACTORY_DIRNAME / ".factory.env"
    gitignore_result = None
    if not skip_gitignore:
        gitignore_result = ensure_gitignore_entries(target_dir)

    workspace_result = None
    if not skip_workspace:
        workspace_result = ensure_workspace_file(
            target_dir,
            workspace_file,
            runtime_config,
            force=force_workspace,
        )

    lock_path = update_lock_file(
        target_dir,
        factory_version=factory_version,
        factory_commit=factory_commit,
        repo_url=repo_url,
        workspace_file=workspace_file,
    )

    return {
        "tmp_dir": tmp_dir,
        "factory_env_path": factory_env_path,
        "factory_env_created": factory_env_created,
        "gitignore_result": gitignore_result,
        "workspace_result": workspace_result,
        "lock_path": lock_path,
        "runtime_manifest_path": runtime_config.runtime_manifest_path,
        "runtime_config": runtime_config,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir = resolve_target_dir(args.target)

    print("=================================================")
    print("🚀 Bootstrapping Host Project")
    print("=================================================")
    print(f"Target Project: {target_dir}")

    try:
        result = bootstrap_target(
            target_dir,
            workspace_file=args.workspace_file,
            skip_workspace=args.skip_workspace,
            force_workspace=args.force_workspace,
            skip_gitignore=args.skip_gitignore,
            factory_version=args.factory_version,
            factory_commit=args.factory_commit,
            repo_url=args.repo_url,
        )
    except FileNotFoundError as exc:
        print(f"❌ {exc}")
        return 1

    print("➡️ Ensured ephemeral state directory...")
    print(f"   [{result['tmp_dir']}] ready.")

    if result["factory_env_created"]:
        print("➡️ Created canonical .factory.env environment contract...")
    else:
        print("➡️ Refreshed canonical .factory.env environment contract...")
    print(f"   [{result['factory_env_path']}] ready.")

    print("➡️ Generated runtime metadata and registered this workspace install...")
    print(f"   [{result['runtime_manifest_path']}] ready.")

    if result["gitignore_result"]:
        gitignore_path, gitignore_updated = result["gitignore_result"]
        status = "updated" if gitignore_updated else "already contained"
        print(f"➡️ .gitignore {status} with factory runtime ignores: [{gitignore_path}]")

    if result["workspace_result"]:
        workspace_path, workspace_status = result["workspace_result"]
        if workspace_status == "skipped-conflict":
            print(
                "➡️ Workspace file preserved because it contains custom edits "
                f"(use --force-workspace to overwrite): [{workspace_path}]"
            )
        else:
            verb = "created" if workspace_status == "created" else "updated"
            print(f"➡️ Host VS Code workspace {verb}: [{workspace_path}]")

    print(f"➡️ Recorded installation metadata: [{result['lock_path']}]")
    print(
        "➡️ Installed update mechanism ready: "
        f"[{target_dir / FACTORY_DIRNAME / 'scripts' / 'factory_update.py'}]"
    )
    print("\n✅ Bootstrap secure and complete!")
    print(
        "Isolation rule confirmed: tool-owned .vscode/ and .github/ remain locked "
        "inside .copilot/softwareFactoryVscode/ and are NOT polluting the root project by default."
    )
    if result["workspace_result"]:
        workspace_path, workspace_status = result["workspace_result"]
        if workspace_status != "skipped-conflict":
            print(
                f"Open `{workspace_path.name}` in VS Code to use the installed agents (Option B)."
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
