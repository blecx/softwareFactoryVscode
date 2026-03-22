#!/usr/bin/env python3
"""Canonical start/stop helper for the Software Factory runtime stack."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Sequence

DEFAULT_WAIT_TIMEOUT = 90
COMPOSE_FILES = [
    "compose/docker-compose.factory.yml",
    "compose/docker-compose.context7.yml",
    "compose/docker-compose.mcp-bash-gateway.yml",
    "compose/docker-compose.repo-fundamentals-mcp.yml",
    "compose/docker-compose.mcp-devops.yml",
    "compose/docker-compose.mcp-offline-docs.yml",
    "compose/docker-compose.mcp-github-ops.yml",
]
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]


def resolve_env_file(repo_root: Path, env_file: Path | None = None) -> Path:
    if env_file is not None:
        return env_file.expanduser().resolve()

    candidates = [repo_root / ".factory.env", repo_root.parent / ".factory.env"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return candidates[0].resolve()


def build_compose_command(
    repo_root: Path,
    env_file: Path,
    action: Sequence[str],
) -> list[str]:
    command = ["docker", "compose", "--env-file", str(env_file)]
    for compose_file in COMPOSE_FILES:
        command.extend(["-f", str((repo_root / compose_file).resolve())])
    command.extend(action)
    return command


def run_compose_command(repo_root: Path, command: Sequence[str]) -> None:
    subprocess.run(
        list(command),
        cwd=str(repo_root),
        check=True,
        text=True,
    )


def start_stack(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    build: bool = True,
    wait: bool = True,
    wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
) -> Path:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    action = ["up", "-d"]
    if build:
        action.append("--build")
    if wait:
        action.extend(["--wait", "--wait-timeout", str(wait_timeout)])

    run_compose_command(
        repo_root,
        build_compose_command(repo_root, resolved_env_file, action),
    )
    return resolved_env_file


def stop_stack(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    remove_volumes: bool = False,
) -> Path:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    action = ["down", "--remove-orphans"]
    if remove_volumes:
        action.append("-v")

    run_compose_command(
        repo_root,
        build_compose_command(repo_root, resolved_env_file, action),
    )
    return resolved_env_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Canonical Software Factory runtime start/stop helper."
    )
    parser.add_argument(
        "command",
        choices=["start", "stop"],
        help="Whether to start or stop the full factory runtime stack.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(SCRIPT_REPO_ROOT),
        help="Factory repository root containing the compose/ directory.",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help="Optional explicit .factory.env path. Defaults to repo-root/.factory.env or repo-root/../.factory.env.",
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="Build images while starting the stack.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Start without Docker Compose health-aware waiting.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=DEFAULT_WAIT_TIMEOUT,
        help=f"Compose wait timeout in seconds (default: {DEFAULT_WAIT_TIMEOUT}).",
    )
    parser.add_argument(
        "--remove-volumes",
        action="store_true",
        help="Also remove named volumes while stopping the stack.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    env_file = Path(args.env_file).expanduser().resolve() if args.env_file else None

    if args.command == "start":
        start_stack(
            repo_root,
            env_file=env_file,
            build=args.build,
            wait=not args.no_wait,
            wait_timeout=args.wait_timeout,
        )
    else:
        stop_stack(
            repo_root,
            env_file=env_file,
            remove_volumes=args.remove_volumes,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
