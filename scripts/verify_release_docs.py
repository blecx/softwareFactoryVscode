#!/usr/bin/env python3
"""Enforce release-documentation and current-release updates when VERSION changes."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

RELEASE_STATUS_HEADING = "## Delivery status snapshot"
RELEASE_STATUS_TABLE_HEADER = "| Scope | Status | Why it matters |"
RELEASE_STATUS_TABLE_DIVIDER = "| --- | --- | --- |"
README_CURRENT_RELEASE_HEADING = "## Current Release"


def run_git(
    repo_root: Path, args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        text=True,
        capture_output=True,
        check=check,
    )


def git_show(repo_root: Path, rev: str, relative_path: Path) -> str:
    result = run_git(
        repo_root,
        ["show", f"{rev}:{relative_path.as_posix()}"],
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def changed_files(repo_root: Path, base_rev: str, head_rev: str) -> set[str]:
    result = run_git(repo_root, ["diff", "--name-only", f"{base_rev}..{head_rev}"])
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def has_release_status_snapshot(release_notes_text: str) -> bool:
    required_markers = (
        RELEASE_STATUS_HEADING,
        RELEASE_STATUS_TABLE_HEADER,
        RELEASE_STATUS_TABLE_DIVIDER,
    )
    return all(marker in release_notes_text for marker in required_markers)


def readme_current_release_matches(
    readme_text: str, *, version: str, expected_release_notes: Path
) -> bool:
    required_markers = (
        README_CURRENT_RELEASE_HEADING,
        f"**Latest release:** `{version}`",
        expected_release_notes.as_posix(),
    )
    return all(marker in readme_text for marker in required_markers)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Require changelog and release notes when VERSION changes."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-rev", required=True)
    parser.add_argument("--head-rev", default="HEAD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    version_path = Path("VERSION")
    changelog_path = Path("CHANGELOG.md")
    manifest_path = Path("manifests") / "release-manifest.json"
    readme_path = Path("README.md")

    base_version = git_show(repo_root, args.base_rev, version_path).strip()
    head_version = git_show(repo_root, args.head_rev, version_path).strip()

    if not head_version:
        print("❌ VERSION is missing in the target revision.")
        return 1

    if base_version == head_version:
        print(
            "ℹ️ VERSION is unchanged; changelog and release notes are not required "
            "for this commit."
        )
        return 0

    changed = changed_files(repo_root, args.base_rev, args.head_rev)
    expected_release_notes = Path(".github") / "releases" / f"v{head_version}.md"
    violations: list[str] = []

    if changelog_path.as_posix() not in changed:
        violations.append(
            f"VERSION changed from `{base_version}` to `{head_version}`, but `{changelog_path}` was not updated."
        )
    else:
        changelog_text = git_show(repo_root, args.head_rev, changelog_path)
        if f"## [{head_version}]" not in changelog_text:
            violations.append(
                f"`{changelog_path}` must contain a `## [{head_version}]` section for the new release."
            )

    if expected_release_notes.as_posix() not in changed:
        violations.append(
            "VERSION changed, but the matching GitHub release notes file was not "
            f"added or updated: `{expected_release_notes.as_posix()}`."
        )
    else:
        release_notes_text = git_show(repo_root, args.head_rev, expected_release_notes)
        if head_version not in release_notes_text:
            violations.append(
                f"`{expected_release_notes.as_posix()}` must mention release `{head_version}`."
            )
        if not has_release_status_snapshot(release_notes_text):
            violations.append(
                f"`{expected_release_notes.as_posix()}` must contain a `{RELEASE_STATUS_HEADING}` section "
                f"with a `{RELEASE_STATUS_TABLE_HEADER}` table so the release's fulfilled scope and open work "
                "stay explicit."
            )

    if readme_path.as_posix() not in changed:
        violations.append(
            f"VERSION changed, but `{readme_path.as_posix()}` was not updated to keep the public current-release section in sync."
        )
    else:
        readme_text = git_show(repo_root, args.head_rev, readme_path)
        if not readme_current_release_matches(
            readme_text,
            version=head_version,
            expected_release_notes=expected_release_notes,
        ):
            violations.append(
                f"`{readme_path.as_posix()}` must keep `{README_CURRENT_RELEASE_HEADING}` in sync with release `{head_version}` and link to `{expected_release_notes.as_posix()}`."
            )

    if manifest_path.as_posix() not in changed:
        violations.append(
            f"VERSION changed, but `{manifest_path.as_posix()}` was not refreshed."
        )
    else:
        manifest_text = git_show(repo_root, args.head_rev, manifest_path)
        try:
            manifest = json.loads(manifest_text)
        except json.JSONDecodeError as exc:
            violations.append(f"`{manifest_path.as_posix()}` is not valid JSON: {exc}")
        else:
            latest = manifest.get("latest", {})
            stable = manifest.get("channels", {}).get("stable", {})
            if latest.get("version_core") != head_version:
                violations.append(
                    f"`{manifest_path.as_posix()}` latest.version_core must be `{head_version}`."
                )
            if stable.get("version_core") != head_version:
                violations.append(
                    f"`{manifest_path.as_posix()}` channels.stable.version_core must be `{head_version}`."
                )

    if violations:
        print("❌ Release bump policy violation(s) detected:")
        for violation in violations:
            print(f"- {violation}")
        print(
            "Release-number increases must update README.md current-release surfaces, CHANGELOG.md, "
            "the matching GitHub release notes file, and the machine-readable release manifest."
        )
        return 1

    print(
        f"✅ Release bump from `{base_version}` to `{head_version}` keeps README current-release surfaces, "
        "changelog, release notes, and refreshed release metadata in sync."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
