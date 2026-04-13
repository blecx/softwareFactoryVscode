#!/usr/bin/env python3
"""Repeatable validation driver for throwaway Option B installation tests.

This script wipes a throwaway target repository, reinstalls the Software Factory
hidden tree from a chosen source ref, runs static compliance verification, and
optionally performs the runtime verification by temporarily handing the shared
localhost MCP ports to the throwaway target.

Guardrail: unless explicitly overridden, the effective throwaway target must
stay inside the source repository's gitignored ``.tmp/`` tree so validation
does not taint unrelated repositories or non-repository paths.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from factory_stack import DEFAULT_WAIT_TIMEOUT
from factory_stack import start_stack as start_factory_stack
from factory_stack import stop_stack as stop_factory_stack

DEFAULT_WORKSPACE_FILE = "software-factory.code-workspace"
DEFAULT_THROWAWAY_TARGET_ROOT = Path(".tmp") / "throwaway-targets"
SNAPSHOT_IGNORE_NAMES = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".tmp",
    "__pycache__",
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run a clean throwaway install validation for Software Factory."
    )
    parser.add_argument(
        "--target",
        required=True,
        help=(
            "Requested throwaway target repository path. Unless "
            "--allow-external-target is set, validation stays inside the "
            "source repository's gitignored .tmp/ tree."
        ),
    )
    parser.add_argument(
        "--source-repo",
        default=str(repo_root),
        help="Source softwareFactoryVscode repository path (default: current repo).",
    )
    parser.add_argument(
        "--factory-ref",
        default="",
        help="Specific source ref/commit to install. Defaults to source HEAD.",
    )
    parser.add_argument(
        "--workspace-file",
        default=DEFAULT_WORKSPACE_FILE,
        help=f"Workspace filename to generate (default: {DEFAULT_WORKSPACE_FILE}).",
    )
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Run only the clean install and static compliance checks.",
    )
    parser.add_argument(
        "--keep-target-running",
        action="store_true",
        help="Leave the throwaway runtime stack running after verification.",
    )
    parser.add_argument(
        "--skip-source-stack-handoff",
        action="store_true",
        help=(
            "Do not stop/restart the source repository stack while validating the "
            "throwaway runtime. Useful for isolated CI/E2E runs."
        ),
    )
    parser.add_argument(
        "--allow-external-target",
        action="store_true",
        help=(
            "Explicitly allow using a throwaway target outside the source "
            "repository's .tmp/ guardrail. Use only when external target "
            "isolation is intentional."
        ),
    )
    return parser.parse_args(argv)


def run_command(command: Sequence[str], *, cwd: Path | None = None) -> None:
    subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
    )


def capture_command(command: Sequence[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def heading(title: str) -> None:
    print("\n" + "=" * 57)
    print(title)
    print("=" * 57)


def resolve_python_executable(repo_root: Path) -> str:
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def resolve_factory_ref(source_repo: Path, requested_ref: str) -> str:
    if requested_ref:
        return requested_ref
    return capture_command(["git", "rev-parse", "HEAD"], cwd=source_repo)


def _snapshot_ignore(_root: str, names: list[str]) -> set[str]:
    return {name for name in names if name in SNAPSHOT_IGNORE_NAMES}


def create_working_tree_snapshot(source_repo: Path) -> Path:
    snapshot_root = Path(tempfile.mkdtemp(prefix="software-factory-snapshot-"))
    snapshot_repo = snapshot_root / source_repo.name
    shutil.copytree(
        source_repo,
        snapshot_repo,
        ignore=_snapshot_ignore,
        symlinks=True,
    )
    run_command(["git", "init", "-b", "main"], cwd=snapshot_repo)
    run_command(
        ["git", "config", "user.name", "Throwaway Validator"], cwd=snapshot_repo
    )
    run_command(
        ["git", "config", "user.email", "throwaway-validator@example.invalid"],
        cwd=snapshot_repo,
    )
    run_command(["git", "add", "."], cwd=snapshot_repo)
    run_command(
        ["git", "commit", "-m", "Throwaway validation snapshot"], cwd=snapshot_repo
    )
    return snapshot_repo


@contextmanager
def prepare_install_source(
    source_repo: Path,
    requested_ref: str,
) -> Iterator[tuple[Path, str, str]]:
    if requested_ref:
        resolved_ref = resolve_factory_ref(source_repo, requested_ref)
        yield source_repo, resolved_ref, "requested ref"
        return

    snapshot_repo = create_working_tree_snapshot(source_repo)
    try:
        yield snapshot_repo, "HEAD", "local working tree snapshot"
    finally:
        shutil.rmtree(snapshot_repo.parent, ignore_errors=True)


def maybe_stop_stack(
    repo_root: Path, env_path: Path, *, remove_volumes: bool = False
) -> bool:
    if not env_path.exists():
        return False

    heading(f"🛑 Stopping stack for {repo_root}")
    stop_factory_stack(
        repo_root,
        env_file=env_path,
        remove_volumes=remove_volumes,
    )
    return True


def start_stack(repo_root: Path, env_path: Path, *, build: bool) -> None:
    heading(f"🚀 Starting stack for {repo_root}")
    start_factory_stack(
        repo_root,
        env_file=env_path,
        build=build,
        wait=True,
        wait_timeout=DEFAULT_WAIT_TIMEOUT,
    )


def wipe_and_reinit_target(target_repo: Path) -> None:
    if target_repo.exists():
        shutil.rmtree(target_repo)
    target_repo.mkdir(parents=True, exist_ok=True)
    run_command(["git", "init", "-b", "main"], cwd=target_repo)


def repo_local_throwaway_root(source_repo: Path) -> Path:
    return (source_repo / DEFAULT_THROWAWAY_TARGET_ROOT).resolve()


def repo_local_throwaway_target(source_repo: Path, requested_target: Path) -> Path:
    target_name = requested_target.name or "throwaway-target"
    return (repo_local_throwaway_root(source_repo) / target_name).resolve()


def is_within_directory(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_effective_target_repo(
    source_repo: Path,
    requested_target: Path,
    *,
    runtime_enabled: bool,
    allow_external_target: bool = False,
) -> tuple[Path, str | None]:
    source_repo = source_repo.expanduser().resolve()
    resolved_target = requested_target.expanduser().resolve()
    repo_tmp_root = (source_repo / ".tmp").resolve()
    if is_within_directory(resolved_target, repo_tmp_root):
        return resolved_target, None

    fallback_target = repo_local_throwaway_target(source_repo, resolved_target)

    if not runtime_enabled:
        if allow_external_target:
            return resolved_target, None
        note = (
            "Requested target is outside the source repository's gitignored .tmp/ "
            "guardrail. Using repository-local throwaway target instead: "
            f"{fallback_target}"
        )
        return fallback_target, note

    if allow_external_target:
        temp_roots = {
            Path(tempfile.gettempdir()).expanduser().resolve(),
            Path("/tmp").resolve(),
            Path("/var/tmp").resolve(),
        }
        if any(
            resolved_target == temp_root or temp_root in resolved_target.parents
            for temp_root in temp_roots
        ):
            note = (
                "Requested target is under the system temporary directory, which may "
                "not be bind-mountable by Docker on this host. "
                f"Using repository-local throwaway target instead: {fallback_target}"
            )
            return fallback_target, note
        return resolved_target, None

    temp_roots = {
        Path(tempfile.gettempdir()).expanduser().resolve(),
        Path("/tmp").resolve(),
        Path("/var/tmp").resolve(),
    }
    if any(
        resolved_target == temp_root or temp_root in resolved_target.parents
        for temp_root in temp_roots
    ):
        note = (
            "Requested target is under the system temporary directory, which may "
            "not be bind-mountable by Docker on this host. "
            f"Using repository-local throwaway target instead: {fallback_target}"
        )
        return fallback_target, note

    note = (
        "Requested target is outside the source repository's gitignored .tmp/ "
        "guardrail. Using repository-local throwaway target instead: "
        f"{fallback_target}"
    )
    return fallback_target, note


def run_install(
    source_repo: Path,
    target_repo: Path,
    factory_ref: str,
    workspace_file: str,
) -> None:
    heading("📦 Installing throwaway target")
    run_command(
        [
            resolve_python_executable(source_repo),
            str(source_repo / "scripts" / "install_factory.py"),
            "--target",
            str(target_repo),
            "--repo-url",
            str(source_repo),
            "--ref",
            factory_ref,
            "--workspace-file",
            workspace_file,
        ],
        cwd=source_repo,
    )


def run_verify(target_repo: Path, *, runtime: bool) -> None:
    heading("🔎 Running compliance verification")
    command = [
        str(
            target_repo / ".copilot/softwareFactoryVscode" / ".venv" / "bin" / "python"
        ),
        str(
            target_repo
            / ".copilot/softwareFactoryVscode"
            / "scripts"
            / "verify_factory_install.py"
        ),
        "--target",
        str(target_repo),
    ]
    if runtime:
        command.extend(["--runtime", "--check-vscode-mcp"])
    run_command(command, cwd=target_repo)


def print_summary(
    target_repo: Path,
    factory_ref: str,
    runtime_checked: bool,
    workspace_file: str,
    install_source_note: str,
) -> None:
    heading("✅ Throwaway validation complete")
    print(f"Target repo:      {target_repo}")
    print(f"Installed ref:    {factory_ref}")
    print(f"Install source:   {install_source_note}")
    print(f"Workspace file:   {target_repo / workspace_file}")
    print("Static verify:    passed")
    print(f"Runtime verify:   {'passed' if runtime_checked else 'skipped'}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    source_repo = Path(args.source_repo).expanduser().resolve()
    source_env = source_repo / ".copilot/softwareFactoryVscode/.factory.env"
    source_stack_stopped = False
    runtime_checked = False

    if not (source_repo / "scripts" / "install_factory.py").exists():
        raise SystemExit(
            f"Source repo does not look like softwareFactoryVscode: {source_repo}"
        )

    target_repo, target_note = resolve_effective_target_repo(
        source_repo,
        Path(args.target),
        runtime_enabled=not args.skip_runtime,
        allow_external_target=args.allow_external_target,
    )
    target_env = target_repo / ".copilot/softwareFactoryVscode/.factory.env"

    with prepare_install_source(source_repo, args.factory_ref) as (
        install_source_repo,
        install_ref,
        install_source_note,
    ):
        heading("🧹 Preparing throwaway target")
        print(f"Using install source: {install_source_note} ({install_source_repo})")
        print(f"Requested target: {Path(args.target).expanduser().resolve()}")
        if target_note:
            print(f"⚠️  {target_note}")
        print(f"Effective target: {target_repo}")
        wipe_and_reinit_target(target_repo)
        run_install(install_source_repo, target_repo, install_ref, args.workspace_file)
        run_verify(target_repo, runtime=False)

        if not args.skip_runtime:
            if source_env.exists() and not args.skip_source_stack_handoff:
                source_stack_stopped = maybe_stop_stack(source_repo, source_env)
            try:
                maybe_stop_stack(
                    target_repo / ".copilot/softwareFactoryVscode",
                    target_env,
                    remove_volumes=True,
                )
                start_stack(
                    target_repo / ".copilot/softwareFactoryVscode",
                    target_env,
                    build=True,
                )
                run_verify(target_repo, runtime=True)
                runtime_checked = True
            finally:
                if not args.keep_target_running and target_env.exists():
                    maybe_stop_stack(
                        target_repo / ".copilot/softwareFactoryVscode",
                        target_env,
                        remove_volumes=True,
                    )
                if source_stack_stopped and not args.skip_source_stack_handoff:
                    start_stack(source_repo, source_env, build=False)

        print_summary(
            target_repo,
            install_ref,
            runtime_checked,
            args.workspace_file,
            install_source_note,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
