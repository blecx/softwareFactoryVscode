#!/usr/bin/env python3
"""Block known placeholder Git identities from entering shared history."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path
from typing import Sequence

BLOCKED_NAMES = {"ci"}
BLOCKED_EMAILS = {"ci@example.com", "ci@localhost"}
COAUTHOR_TRAILER_PATTERN = re.compile(
    r"^Co-authored-by:\s*(?P<name>[^<]+?)\s*<(?P<email>[^>]+)>\s*$",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    return value.strip().casefold()


def identity_is_blocked(name: str, email: str) -> bool:
    normalized_name = normalize_text(name)
    normalized_email = normalize_text(email)
    return normalized_name in BLOCKED_NAMES or normalized_email in BLOCKED_EMAILS


def extract_blocked_coauthor_trailers(message: str) -> list[str]:
    blocked: list[str] = []
    for line in message.splitlines():
        match = COAUTHOR_TRAILER_PATTERN.match(line.strip())
        if match is None:
            continue
        name = match.group("name")
        email = match.group("email")
        if identity_is_blocked(name, email):
            blocked.append(f"{name.strip()} <{email.strip()}>")
    return blocked


def run_git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def read_git_config_value(repo_root: Path, key: str) -> str:
    result = run_git(repo_root, ["config", "--get", key])
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def load_head_metadata(
    repo_root: Path, head_rev: str
) -> tuple[str, str, str, str, str] | None:
    result = run_git(
        repo_root,
        ["show", "--quiet", "--format=%an%x00%ae%x00%cn%x00%ce%x00%B", head_rev],
    )
    if result.returncode != 0:
        return None

    parts = result.stdout.split("\x00", 4)
    if len(parts) != 5:
        return None
    return tuple(part.strip("\n") for part in parts)  # type: ignore[return-value]


def collect_findings(repo_root: Path, head_rev: str) -> tuple[list[str], str | None]:
    findings: list[str] = []
    config_name = read_git_config_value(repo_root, "user.name")
    config_email = read_git_config_value(repo_root, "user.email")
    if config_name or config_email:
        if identity_is_blocked(config_name, config_email):
            findings.append(
                "Configured Git identity is blocked: "
                f"`{config_name or '<missing name>'} <{config_email or '<missing email>'}>`."
            )

    metadata = load_head_metadata(repo_root, head_rev)
    if metadata is None:
        return findings, (
            "Unable to read HEAD commit metadata. Confirm the repository and "
            f"revision `{head_rev}` are valid."
        )

    author_name, author_email, committer_name, committer_email, message = metadata
    if identity_is_blocked(author_name, author_email):
        findings.append(
            "HEAD author uses a blocked placeholder identity: "
            f"`{author_name} <{author_email}>`."
        )
    if identity_is_blocked(committer_name, committer_email):
        findings.append(
            "HEAD committer uses a blocked placeholder identity: "
            f"`{committer_name} <{committer_email}>`."
        )

    blocked_trailers = extract_blocked_coauthor_trailers(message)
    if blocked_trailers:
        findings.append(
            "HEAD commit message contains blocked `Co-authored-by` trailer(s): "
            + ", ".join(f"`{trailer}`" for trailer in blocked_trailers)
            + "."
        )

    return findings, None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify that Git identity metadata does not use blocked placeholders."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--head-rev", default="HEAD")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    findings, error = collect_findings(repo_root, args.head_rev.strip() or "HEAD")

    if error is not None:
        print(f"❌ {error}")
        return 1

    if findings:
        print("❌ Git author identity guard detected blocked placeholder metadata.")
        for finding in findings:
            print(f"- {finding}")
        print(
            "Fix the local Git identity, then amend or rewrite the affected commit(s) "
            "to remove `CI <ci@example.com>` / `CI <ci@localhost>` author, "
            "committer, and `Co-authored-by` metadata before rerunning this guard."
        )
        return 1

    print("✅ Git author identity guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
