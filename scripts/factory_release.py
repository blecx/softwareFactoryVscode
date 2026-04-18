#!/usr/bin/env python3
"""Structured release metadata helpers for Software Factory installs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import urlopen

RELEASE_MANIFEST_RELATIVE_PATH = Path("manifests") / "release-manifest.json"
RELEASE_METADATA_SCHEMA = 1
DEFAULT_CHANNEL = "stable"
DEFAULT_BRANCH = "main"
VERSION_PATTERN = re.compile(
    r"^(?P<major>\d+)\.(?P<minor>\d+)(?:\.(?P<patch>\d+))?(?:-(?P<prerelease>[0-9A-Za-z.-]+))?$"
)
GITHUB_HTTPS_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?/?$"
)
GITHUB_SSH_PATTERN = re.compile(
    r"^git@github\.com:(?P<owner>[^/]+)/(?P<repo>[^/.]+?)(?:\.git)?$"
)


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
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def run_git_command(
    repo_dir: Path,
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_dir), *args],
        check=check,
        text=True,
        capture_output=True,
    )


def git_output(repo_dir: Path, args: list[str]) -> str:
    try:
        return run_git_command(repo_dir, args).stdout.strip()
    except subprocess.CalledProcessError:
        return ""


def read_version_core(repo_dir: Path) -> str:
    version_file = repo_dir / "VERSION"
    if version_file.exists():
        value = version_file.read_text(encoding="utf-8").strip()
        if value:
            return value
    return DEFAULT_BRANCH


def normalize_version(version: str) -> str:
    match = VERSION_PATTERN.match(version.strip())
    if not match:
        return version.strip()
    patch = match.group("patch") or "0"
    prerelease = match.group("prerelease")
    normalized = f"{match.group('major')}.{match.group('minor')}.{patch}"
    if prerelease:
        normalized += f"-{prerelease}"
    return normalized


def semver_key(version: str) -> tuple[int, int, int, int, str]:
    match = VERSION_PATTERN.match(version.strip())
    if not match:
        return (-1, -1, -1, -1, version.strip())
    prerelease = match.group("prerelease") or ""
    return (
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch") or "0"),
        0 if prerelease else 1,
        prerelease,
    )


def compare_versions(left: str, right: str) -> int:
    left_key = semver_key(normalize_version(left))
    right_key = semver_key(normalize_version(right))
    if left_key < right_key:
        return -1
    if left_key > right_key:
        return 1
    return 0


def current_branch(repo_dir: Path) -> str:
    return git_output(repo_dir, ["branch", "--show-current"]) or DEFAULT_BRANCH


def head_commit(repo_dir: Path) -> str:
    return git_output(repo_dir, ["rev-parse", "HEAD"])


def short_commit(commit_sha: str) -> str:
    return commit_sha[:7] if commit_sha else ""


def commit_timestamp(repo_dir: Path) -> str:
    value = git_output(repo_dir, ["show", "-s", "--format=%cI", "HEAD"])
    return value or utc_now_iso()


def total_commit_count(repo_dir: Path) -> int:
    value = git_output(repo_dir, ["rev-list", "--count", "HEAD"])
    try:
        return int(value)
    except ValueError:
        return 0


def find_matching_version_tag(repo_dir: Path, version_core: str) -> str:
    normalized = normalize_version(version_core)
    candidates = [f"v{version_core}"]
    if normalized != version_core:
        candidates.append(f"v{normalized}")
    for candidate in candidates:
        result = run_git_command(
            repo_dir, ["rev-parse", "-q", "--verify", candidate], check=False
        )
        if result.returncode == 0:
            return candidate
    return ""


def build_number(repo_dir: Path, version_core: str) -> int:
    version_tag = find_matching_version_tag(repo_dir, version_core)
    if version_tag:
        value = git_output(repo_dir, ["rev-list", "--count", f"{version_tag}..HEAD"])
        try:
            return int(value)
        except ValueError:
            return 0
    return total_commit_count(repo_dir)


def infer_channel(version_core: str, source_ref: str) -> str:
    normalized = normalize_version(version_core)
    if "-" in normalized:
        return "prerelease"
    lowered_ref = source_ref.strip().lower()
    if lowered_ref in {"main", "master", DEFAULT_BRANCH}:
        return DEFAULT_CHANNEL
    return "custom"


def parse_github_repo(repo_url: str) -> tuple[str, str] | None:
    for pattern in (GITHUB_HTTPS_PATTERN, GITHUB_SSH_PATTERN):
        match = pattern.match(repo_url.strip())
        if match:
            return match.group("owner"), match.group("repo")
    return None


def build_manifest_url(repo_url: str, ref: str = DEFAULT_BRANCH) -> str:
    parsed = parse_github_repo(repo_url)
    if not parsed:
        return ""
    owner, repo = parsed
    resolved_ref = ref.strip() or DEFAULT_BRANCH
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/"
        f"{resolved_ref}/{RELEASE_MANIFEST_RELATIVE_PATH.as_posix()}"
    )


def build_release_metadata(
    repo_dir: Path,
    *,
    repo_url: str = "",
    source_ref: str = "",
    channel: str = "",
) -> dict[str, Any]:
    version_core = read_version_core(repo_dir)
    normalized_version = normalize_version(version_core)
    commit_sha = head_commit(repo_dir)
    commit_short = short_commit(commit_sha)
    resolved_ref = source_ref.strip() or current_branch(repo_dir)
    resolved_channel = channel.strip() or infer_channel(version_core, resolved_ref)
    release_build_number = build_number(repo_dir, version_core)
    version_tag = find_matching_version_tag(repo_dir, version_core)
    display_version = version_core
    if commit_short:
        display_version = f"{version_core}+{release_build_number}.g{commit_short}"
    manifest_url = build_manifest_url(repo_url, DEFAULT_BRANCH)
    return {
        "schema_version": RELEASE_METADATA_SCHEMA,
        "version_core": version_core,
        "normalized_version": normalized_version,
        "display_version": display_version,
        "channel": resolved_channel,
        "build_number": release_build_number,
        "commit_sha": commit_sha,
        "commit_short": commit_short,
        "version_tag": version_tag,
        "source_ref": resolved_ref,
        "repo_url": repo_url,
        "manifest_path": RELEASE_MANIFEST_RELATIVE_PATH.as_posix(),
        "manifest_url": manifest_url,
        "generated_at": commit_timestamp(repo_dir),
    }


def build_release_manifest(
    repo_dir: Path,
    *,
    repo_url: str = "",
    source_ref: str = DEFAULT_BRANCH,
) -> dict[str, Any]:
    release = build_release_metadata(
        repo_dir,
        repo_url=repo_url,
        source_ref=source_ref,
    )
    return {
        "schema_version": RELEASE_METADATA_SCHEMA,
        "generated_at": release["generated_at"],
        "source": {
            "repo_url": repo_url,
            "default_branch": DEFAULT_BRANCH,
            "manifest_path": RELEASE_MANIFEST_RELATIVE_PATH.as_posix(),
            "manifest_url": build_manifest_url(repo_url, DEFAULT_BRANCH),
        },
        "latest": release,
        "channels": {
            DEFAULT_CHANNEL: {
                **release,
                "channel": DEFAULT_CHANNEL,
                "source_ref": DEFAULT_BRANCH,
            }
        },
        "update_policy": {
            "minimum_lock_schema": RELEASE_METADATA_SCHEMA,
            "minimum_release_schema": RELEASE_METADATA_SCHEMA,
            "auto_update_level": "patch",
            "manual_review_for_minor": True,
            "manual_review_for_major": True,
        },
    }


def build_lock_release_metadata(
    repo_dir: Path,
    *,
    repo_url: str = "",
    source_ref: str = "",
    version_core: str = "",
    commit_sha: str = "",
) -> dict[str, Any]:
    release = build_release_metadata(
        repo_dir,
        repo_url=repo_url,
        source_ref=source_ref,
    )
    resolved_version = version_core.strip()
    resolved_commit = commit_sha.strip()
    if resolved_version:
        release["version_core"] = resolved_version
        release["normalized_version"] = normalize_version(resolved_version)
    if resolved_commit:
        release["commit_sha"] = resolved_commit
        release["commit_short"] = short_commit(resolved_commit)
    if release.get("commit_short"):
        release["display_version"] = (
            f"{release['version_core']}+{release['build_number']}.g{release['commit_short']}"
        )
    else:
        release["display_version"] = release["version_core"]
    return {
        **release,
        "lock_schema": RELEASE_METADATA_SCHEMA,
    }


def write_release_manifest_file(
    repo_dir: Path,
    *,
    repo_url: str = "",
    source_ref: str = DEFAULT_BRANCH,
    output_path: Path | None = None,
) -> Path:
    manifest = build_release_manifest(
        repo_dir,
        repo_url=repo_url,
        source_ref=source_ref,
    )
    path = output_path or (repo_dir / RELEASE_MANIFEST_RELATIVE_PATH)
    write_json(path, manifest)
    return path


def load_release_manifest_from_repo(repo_dir: Path) -> dict[str, Any]:
    return load_json(repo_dir / RELEASE_MANIFEST_RELATIVE_PATH)


def fetch_release_manifest(
    *,
    repo_url: str,
    source_ref: str = DEFAULT_BRANCH,
    local_repo_dir: Path | None = None,
    timeout: float = 5.0,
) -> dict[str, Any]:
    if repo_url and Path(repo_url).expanduser().exists():
        local_repo_root = Path(repo_url).expanduser().resolve()
        return build_release_manifest(
            local_repo_root,
            repo_url=repo_url,
            source_ref=source_ref,
        )

    manifest_url = build_manifest_url(repo_url, DEFAULT_BRANCH)
    if manifest_url:
        with urlopen(manifest_url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    if local_repo_dir is not None:
        resolved_ref = source_ref.strip() or DEFAULT_BRANCH
        show_target = (
            f"origin/{resolved_ref}:{RELEASE_MANIFEST_RELATIVE_PATH.as_posix()}"
        )
        result = run_git_command(
            local_repo_dir,
            ["show", show_target],
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)

    raise RuntimeError(
        "Unable to resolve release manifest from the configured repository source."
    )


def extract_installed_release(lock_data: dict[str, Any]) -> dict[str, Any]:
    release = lock_data.get("release")
    if isinstance(release, dict):
        version_core = str(release.get("version_core", "")).strip()
        if version_core:
            return release

    factory_data = lock_data.get("factory", {})
    factory_data = factory_data if isinstance(factory_data, dict) else {}
    commit_sha = str(factory_data.get("commit", "")).strip()
    version_core = str(lock_data.get("version", "")).strip()
    return {
        "schema_version": 0,
        "version_core": version_core,
        "normalized_version": normalize_version(version_core),
        "display_version": version_core,
        "channel": DEFAULT_CHANNEL,
        "build_number": 0,
        "commit_sha": commit_sha,
        "commit_short": short_commit(commit_sha),
        "version_tag": "",
        "source_ref": DEFAULT_BRANCH,
        "repo_url": str(factory_data.get("repo_url", "")).strip(),
        "manifest_path": RELEASE_MANIFEST_RELATIVE_PATH.as_posix(),
        "manifest_url": build_manifest_url(
            str(factory_data.get("repo_url", "")), DEFAULT_BRANCH
        ),
        "generated_at": str(lock_data.get("updated_at", "")).strip(),
    }


def compare_release_state(
    installed_release: dict[str, Any],
    latest_release: dict[str, Any],
    *,
    update_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = update_policy if isinstance(update_policy, dict) else {}
    installed_version = str(installed_release.get("version_core", "")).strip()
    latest_version = str(latest_release.get("version_core", "")).strip()
    installed_commit = str(installed_release.get("commit_sha", "")).strip()
    latest_commit = str(latest_release.get("commit_sha", "")).strip()
    installed_build = int(installed_release.get("build_number", 0) or 0)
    latest_build = int(latest_release.get("build_number", 0) or 0)

    status = "up-to-date"
    reason = "Installed factory matches the latest release metadata."
    if installed_commit and latest_commit and installed_commit == latest_commit:
        status = "up-to-date"
    else:
        version_cmp = compare_versions(installed_version, latest_version)
        if version_cmp < 0:
            status = "update-available"
            reason = f"Installed release `{installed_version}` is behind latest `{latest_version}`."
        elif version_cmp == 0 and installed_build < latest_build:
            status = "update-available"
            reason = (
                "Installed factory is on the same release line but behind the latest "
                f"build (`{installed_build}` < `{latest_build}`)."
            )
        elif installed_commit != latest_commit:
            status = "local-drift"
            reason = (
                "Installed factory commit differs from the latest manifest commit on the "
                "same release line."
            )

    mandatory = False
    minimum_lock_schema = int(policy.get("minimum_lock_schema", 0) or 0)
    if int(installed_release.get("schema_version", 0) or 0) < minimum_lock_schema:
        status = "mandatory-update"
        mandatory = True
        reason = (
            "Installed release metadata schema is older than the minimum supported "
            f"schema `{minimum_lock_schema}`."
        )

    return {
        "status": status,
        "mandatory": mandatory,
        "installed": installed_release,
        "latest": latest_release,
        "reason": reason,
        "update_available": status in {"update-available", "mandatory-update"},
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and inspect Software Factory release metadata."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    parser_describe = subparsers.add_parser(
        "describe", help="Print current release metadata as JSON."
    )
    parser_describe.add_argument("--repo-root", default=".")
    parser_describe.add_argument("--repo-url", default="")
    parser_describe.add_argument("--ref", default=DEFAULT_BRANCH)

    parser_write = subparsers.add_parser(
        "write-manifest", help="Write or validate the release manifest."
    )
    parser_write.add_argument("--repo-root", default=".")
    parser_write.add_argument("--repo-url", default="")
    parser_write.add_argument("--ref", default=DEFAULT_BRANCH)
    parser_write.add_argument("--output", default="")
    parser_write.add_argument("--check", action="store_true")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()

    if args.command == "describe":
        metadata = build_release_metadata(
            repo_root,
            repo_url=args.repo_url,
            source_ref=args.ref,
        )
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        return 0

    output_path = Path(args.output).expanduser().resolve() if args.output else None
    manifest = build_release_manifest(
        repo_root,
        repo_url=args.repo_url,
        source_ref=args.ref,
    )
    target_path = output_path or (repo_root / RELEASE_MANIFEST_RELATIVE_PATH)
    rendered = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    if args.check:
        existing = (
            target_path.read_text(encoding="utf-8") if target_path.exists() else ""
        )

        # Compare ignoring volatile git fields
        if existing:
            try:
                existing_json = json.loads(existing)
                # Copy volatile fields from existing so it matches if only these differ
                for field in [
                    "commit_sha",
                    "commit_short",
                    "display_version",
                    "generated_at",
                    "build_number",
                ]:
                    if field in existing_json.get("latest", {}):
                        manifest["latest"][field] = existing_json["latest"][field]
                    if (
                        "stable" in existing_json.get("channels", {})
                        and field in existing_json["channels"]["stable"]
                    ):
                        manifest["channels"]["stable"][field] = existing_json[
                            "channels"
                        ]["stable"][field]
                if "generated_at" in existing_json:
                    manifest["generated_at"] = existing_json["generated_at"]

                rendered_for_check = (
                    json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
                )

                if existing != rendered_for_check:
                    print(f"Release manifest drift detected: {target_path}")
                    return 1
                print(f"Release manifest is current: {target_path}")
                return 0
            except json.JSONDecodeError:
                pass

        if existing != rendered:
            print(f"Release manifest drift detected: {target_path}")
            return 1
        print(f"Release manifest is current: {target_path}")
        return 0

    write_json(target_path, manifest)
    print(f"Wrote release manifest: {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
