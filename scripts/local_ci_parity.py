#!/usr/bin/env python3
"""Run local CI-parity prechecks for softwareFactoryVscode.

This script mirrors `.github/workflows/ci.yml` checks where they are executable
locally. Docker image build validation is available via `--include-docker-build`
but is optional by default because it is slower and host-dependent.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Sequence

DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"


def run_command(command: Sequence[str], *, cwd: Path) -> None:
    subprocess.run(
        list(command),
        cwd=str(cwd),
        check=True,
        text=True,
    )


def run_step(name: str, command: Sequence[str], *, cwd: Path) -> None:
    print(f"\n▶ {name}")
    run_command(command, cwd=cwd)


def run_git(repo_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        text=True,
        capture_output=True,
    )


def git_ref_exists(repo_root: Path, ref: str) -> bool:
    result = run_git(repo_root, ["rev-parse", "--verify", ref])
    return result.returncode == 0


def resolve_base_rev(repo_root: Path, *, base_rev: str, head_rev: str) -> str:
    if base_rev.strip():
        return base_rev.strip()

    if git_ref_exists(repo_root, "origin/main") and git_ref_exists(repo_root, head_rev):
        merge_base = run_git(repo_root, ["merge-base", head_rev, "origin/main"])
        if merge_base.returncode == 0 and merge_base.stdout.strip():
            return merge_base.stdout.strip()

    head_parent = f"{head_rev}^"
    if git_ref_exists(repo_root, head_parent):
        return head_parent

    return head_rev


def run_docker_build_validation(repo_root: Path) -> None:
    if shutil.which("docker") is None:
        raise RuntimeError(
            "Docker CLI is required for --include-docker-build but is not available on PATH."
        )

    dockerfiles = sorted((repo_root / "docker").glob("*/Dockerfile"))
    if not dockerfiles:
        raise RuntimeError("No Dockerfiles found under docker/*/Dockerfile.")

    for dockerfile in dockerfiles:
        service = dockerfile.parent.name
        run_step(
            f"Docker build validation ({service})",
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                ".",
                "--quiet",
                "--tag",
                f"factory-local-{service}:precheck",
            ],
            cwd=repo_root,
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local CI-parity checks before PR finalization."
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--base-rev", default="")
    parser.add_argument("--head-rev", default="HEAD")
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used for quality/test commands.",
    )
    parser.add_argument(
        "--pr-body-file",
        default="",
        help="Optional PR body file to validate with scripts/validate-pr-template.sh.",
    )
    parser.add_argument(
        "--skip-integration",
        action="store_true",
        help="Skip ./tests/run-integration-test.sh (faster local iteration mode).",
    )
    parser.add_argument(
        "--skip-pr-template-check",
        action="store_true",
        help="Skip PR template/body validation checks.",
    )
    parser.add_argument(
        "--include-docker-build",
        action="store_true",
        help="Also run docker/*/Dockerfile build parity checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    base_rev = resolve_base_rev(
        repo_root,
        base_rev=args.base_rev,
        head_rev=args.head_rev,
    )

    print("=" * 60)
    print("Local CI-parity precheck")
    print("=" * 60)
    print(f"repo_root={repo_root}")
    print(f"base_rev={base_rev}")
    print(f"head_rev={args.head_rev}")

    run_step(
        "Release docs policy check",
        [
            args.python,
            "./scripts/verify_release_docs.py",
            "--repo-root",
            ".",
            "--base-rev",
            base_rev,
            "--head-rev",
            args.head_rev,
        ],
        cwd=repo_root,
    )

    run_step(
        "Release manifest parity check",
        [
            args.python,
            "./scripts/factory_release.py",
            "write-manifest",
            "--repo-root",
            ".",
            "--repo-url",
            DEFAULT_REPO_URL,
            "--check",
        ],
        cwd=repo_root,
    )

    run_step(
        "Black format check",
        [
            args.python,
            "-m",
            "black",
            "--check",
            "factory_runtime/",
            "scripts/",
            "tests/",
        ],
        cwd=repo_root,
    )

    run_step(
        "isort import-order check",
        [
            args.python,
            "-m",
            "isort",
            "--check-only",
            "factory_runtime/",
            "scripts/",
            "tests/",
        ],
        cwd=repo_root,
    )

    run_step(
        "Flake8 lint check",
        [
            args.python,
            "-m",
            "flake8",
            "factory_runtime/",
            "scripts/",
            "tests/",
            "--max-line-length=120",
            "--ignore=E203,W503,E402,E731,F401,F841",
        ],
        cwd=repo_root,
    )

    run_step(
        "Pytest suite (tests/)",
        [args.python, "-m", "pytest", "tests/"],
        cwd=repo_root,
    )

    if args.skip_integration:
        print("\nℹ️ Skipping integration regression by request (--skip-integration).")
    else:
        run_step(
            "Integration regression",
            ["bash", "./tests/run-integration-test.sh"],
            cwd=repo_root,
        )

    if args.skip_pr_template_check:
        print(
            "ℹ️ Skipping PR-template validation by request (--skip-pr-template-check)."
        )
    else:
        run_step(
            "PR-template format validation (.github/pull_request_template.md)",
            [
                "bash",
                "./scripts/validate-pr-template.sh",
                "./.github/pull_request_template.md",
            ],
            cwd=repo_root,
        )
        if args.pr_body_file.strip():
            run_step(
                "PR-template format validation (provided PR body)",
                [
                    "bash",
                    "./scripts/validate-pr-template.sh",
                    str(Path(args.pr_body_file).expanduser().resolve()),
                ],
                cwd=repo_root,
            )

    if args.include_docker_build:
        run_docker_build_validation(repo_root)
    else:
        print(
            "\nℹ️ Docker image build parity is skipped by default. "
            "Run again with --include-docker-build for full container-build parity."
        )

    print("\n✅ Local CI-parity checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
