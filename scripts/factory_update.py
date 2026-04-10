#!/usr/bin/env python3
"""Check for and apply Software Factory updates from the configured source repo."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bootstrap_host
import factory_release
import install_factory

FACTORY_DIRNAME = bootstrap_host.FACTORY_DIRNAME
DEFAULT_WORKSPACE_FILENAME = bootstrap_host.DEFAULT_WORKSPACE_FILENAME


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check for or apply Software Factory updates in an installed workspace."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command_name in ("check", "apply"):
        subparser = subparsers.add_parser(command_name)
        subparser.add_argument("--target", default=".")
        subparser.add_argument("--repo-url", default="")
        subparser.add_argument("--ref", default=factory_release.DEFAULT_BRANCH)
        subparser.add_argument("--workspace-file", default=DEFAULT_WORKSPACE_FILENAME)
        subparser.add_argument("--timeout", type=float, default=5.0)
        subparser.add_argument("--json", action="store_true")

    return parser.parse_args(argv)


def load_lock_data(target_dir: Path) -> dict[str, Any]:
    lock_path = target_dir / FACTORY_DIRNAME / "lock.json"
    if not lock_path.exists():
        raise FileNotFoundError(f"Missing installation metadata lock file: {lock_path}")
    return bootstrap_host.load_json(lock_path)


def resolve_repo_url(
    *,
    explicit_repo_url: str,
    lock_data: dict[str, Any],
    factory_dir: Path,
) -> str:
    if explicit_repo_url.strip():
        return explicit_repo_url.strip()

    factory_data = lock_data.get("factory", {})
    if isinstance(factory_data, dict):
        repo_url = str(factory_data.get("repo_url", "")).strip()
        if repo_url:
            return repo_url

    return (
        bootstrap_host.read_factory_repo_url(factory_dir)
        or install_factory.DEFAULT_REPO_URL
    )


def resolve_source_ref(lock_data: dict[str, Any], explicit_ref: str) -> str:
    if explicit_ref.strip():
        return explicit_ref.strip()
    release_data = lock_data.get("release")
    if isinstance(release_data, dict):
        source_ref = str(release_data.get("source_ref", "")).strip()
        if source_ref:
            return source_ref
    return factory_release.DEFAULT_BRANCH


def check_for_updates(
    target_dir: Path,
    *,
    repo_url: str,
    source_ref: str,
    timeout: float,
) -> dict[str, Any]:
    factory_dir = target_dir / FACTORY_DIRNAME
    lock_data = load_lock_data(target_dir)
    if factory_dir.exists():
        subprocess.run(
            ["git", "-C", str(factory_dir), "fetch", "origin", "--prune"],
            check=False,
            text=True,
            capture_output=True,
        )

    manifest = factory_release.fetch_release_manifest(
        repo_url=repo_url,
        source_ref=source_ref,
        local_repo_dir=factory_dir if factory_dir.exists() else None,
        timeout=timeout,
    )
    installed_release = factory_release.extract_installed_release(lock_data)
    latest_release = manifest.get("channels", {}).get(
        factory_release.DEFAULT_CHANNEL,
        manifest.get("latest", {}),
    )
    comparison = factory_release.compare_release_state(
        installed_release,
        latest_release if isinstance(latest_release, dict) else {},
        update_policy=manifest.get("update_policy", {}),
    )
    return {
        **comparison,
        "manifest": manifest,
        "repo_url": repo_url,
        "source_ref": source_ref,
        "target_dir": str(target_dir),
    }


def print_update_report(report: dict[str, Any]) -> None:
    installed = report["installed"]
    latest = report["latest"]
    print(f"update_status={report['status']}")
    print(f"update_available={str(report['update_available']).lower()}")
    print(f"mandatory={str(report['mandatory']).lower()}")
    print(f"repo_url={report['repo_url']}")
    print(f"source_ref={report['source_ref']}")
    print(
        f"installed_version={installed.get('display_version', installed.get('version_core', ''))}"
    )
    print(f"installed_commit={installed.get('commit_sha', '')}")
    print(
        f"latest_version={latest.get('display_version', latest.get('version_core', ''))}"
    )
    print(f"latest_commit={latest.get('commit_sha', '')}")
    print(f"manifest_url={latest.get('manifest_url', '')}")
    print(f"reason={report['reason']}")


def apply_update(args: argparse.Namespace) -> int:
    target_dir = bootstrap_host.resolve_target_dir(args.target)
    lock_data = load_lock_data(target_dir)
    factory_dir = target_dir / FACTORY_DIRNAME
    repo_url = resolve_repo_url(
        explicit_repo_url=args.repo_url,
        lock_data=lock_data,
        factory_dir=factory_dir,
    )
    source_ref = resolve_source_ref(lock_data, args.ref)
    report = check_for_updates(
        target_dir,
        repo_url=repo_url,
        source_ref=source_ref,
        timeout=args.timeout,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_update_report(report)

    if not report["update_available"]:
        print("✅ Factory install is already current; no update applied.")
        return 0

    installer_args = [
        "--target",
        str(target_dir),
        "--repo-url",
        repo_url,
        "--update",
        "--workspace-file",
        args.workspace_file,
    ]
    latest_ref = str(report["latest"].get("source_ref", source_ref)).strip()
    if latest_ref:
        installer_args.extend(["--ref", latest_ref])

    print("➡️ Applying update via the canonical installer...")
    return install_factory.main(installer_args)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir = bootstrap_host.resolve_target_dir(args.target)
    lock_data = load_lock_data(target_dir)
    factory_dir = target_dir / FACTORY_DIRNAME
    repo_url = resolve_repo_url(
        explicit_repo_url=args.repo_url,
        lock_data=lock_data,
        factory_dir=factory_dir,
    )
    source_ref = resolve_source_ref(lock_data, args.ref)

    report = check_for_updates(
        target_dir,
        repo_url=repo_url,
        source_ref=source_ref,
        timeout=args.timeout,
    )

    if args.command == "apply":
        return apply_update(args)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_update_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
