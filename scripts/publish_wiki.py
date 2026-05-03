#!/usr/bin/env python3
"""Safely publish the canonical live wiki clone for this repository."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELATIVE_WIKI_DIR = Path(".tmp") / "wiki-launch" / "live-wiki"
DEFAULT_PUBLISH_BRANCH = "master"


def run_git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def _format_git_error(prefix: str, result: subprocess.CompletedProcess[str]) -> str:
    output = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
    return f"{prefix} {output}".strip() if output else prefix


def require_git_stdout(repo_root: Path, args: Sequence[str], prefix: str) -> str:
    result = run_git(repo_root, args)
    if result.returncode != 0:
        raise RuntimeError(_format_git_error(prefix, result))
    return (result.stdout or "").strip()


def resolve_repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is None:
        return REPO_ROOT
    return Path(repo_root).expanduser().resolve()


def resolve_wiki_dir(repo_root: Path, wiki_dir: str | Path | None = None) -> Path:
    expected = (repo_root / DEFAULT_RELATIVE_WIKI_DIR).resolve()
    candidate = expected
    if wiki_dir not in (None, ""):
        candidate = Path(wiki_dir).expanduser().resolve()
    if candidate != expected:
        raise ValueError(
            "Wiki publish helper only supports the canonical live wiki clone at "
            f"`{expected}`."
        )
    return expected


def ensure_wiki_git_worktree(wiki_dir: Path) -> None:
    inside = require_git_stdout(
        wiki_dir,
        ["rev-parse", "--is-inside-work-tree"],
        "Unable to verify that the wiki directory is a git worktree.",
    )
    if inside != "true":
        raise RuntimeError(
            "The canonical live wiki directory is not recognized as a git worktree."
        )


def ensure_clean_worktree(wiki_dir: Path) -> None:
    porcelain = require_git_stdout(
        wiki_dir,
        ["status", "--porcelain"],
        "Unable to read wiki worktree status.",
    )
    if porcelain:
        raise RuntimeError(
            "The canonical live wiki clone has uncommitted changes. Commit or stash "
            "them before publishing."
        )


def resolve_publish_branch(wiki_dir: Path, branch: str) -> str:
    current_branch = require_git_stdout(
        wiki_dir,
        ["rev-parse", "--abbrev-ref", "HEAD"],
        "Unable to resolve the current wiki branch.",
    )
    if not current_branch or current_branch == "HEAD":
        raise RuntimeError(
            "The canonical live wiki clone is on a detached HEAD. Check out the "
            "publish branch before running this helper."
        )

    target_branch = branch.strip() or current_branch
    if current_branch != target_branch:
        raise RuntimeError(
            "The canonical live wiki clone is checked out on "
            f"`{current_branch}` but the requested publish branch is "
            f"`{target_branch}`. Switch branches or pass `--branch {current_branch}` "
            "explicitly if that branch is the intended publish target."
        )
    return current_branch


def ensure_remote_exists(wiki_dir: Path, remote: str) -> None:
    require_git_stdout(
        wiki_dir,
        ["remote", "get-url", remote],
        f"Unable to resolve git remote `{remote}` for the canonical live wiki clone.",
    )


def publish_wiki_clone(
    *,
    repo_root: str | Path | None = None,
    wiki_dir: str | Path | None = None,
    remote: str = "origin",
    branch: str = DEFAULT_PUBLISH_BRANCH,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_repo_root = resolve_repo_root(repo_root)
    resolved_wiki_dir = resolve_wiki_dir(resolved_repo_root, wiki_dir)
    ensure_wiki_git_worktree(resolved_wiki_dir)
    ensure_clean_worktree(resolved_wiki_dir)
    publish_branch = resolve_publish_branch(resolved_wiki_dir, branch)
    ensure_remote_exists(resolved_wiki_dir, remote)

    head_sha = require_git_stdout(
        resolved_wiki_dir,
        ["rev-parse", "HEAD"],
        "Unable to resolve the wiki HEAD revision.",
    )
    status_summary = require_git_stdout(
        resolved_wiki_dir,
        ["status", "--short", "--branch"],
        "Unable to read the wiki status summary.",
    )

    payload: dict[str, Any] = {
        "repoRoot": str(resolved_repo_root),
        "wikiDir": str(resolved_wiki_dir),
        "remote": remote,
        "branch": publish_branch,
        "head": head_sha,
        "status": status_summary,
        "dryRun": dry_run,
        "pushed": False,
    }
    if dry_run:
        return payload

    push_args = ["push", remote, f"{publish_branch}:{publish_branch}"]
    result = run_git(resolved_wiki_dir, push_args)
    if result.returncode != 0:
        raise RuntimeError(
            _format_git_error(
                "Unable to publish the canonical live wiki clone.",
                result,
            )
        )

    payload["pushed"] = True
    if result.stdout:
        payload["stdout"] = result.stdout.strip()
    if result.stderr:
        payload["stderr"] = result.stderr.strip()
    return payload


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Publish the canonical .tmp/wiki-launch/live-wiki clone using the "
            "repo-owned helper instead of raw git push instructions."
        )
    )
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--wiki-dir", default="")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--branch", default=DEFAULT_PUBLISH_BRANCH)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        payload = publish_wiki_clone(
            repo_root=args.repo_root,
            wiki_dir=args.wiki_dir,
            remote=args.remote,
            branch=args.branch,
            dry_run=args.dry_run,
        )
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
