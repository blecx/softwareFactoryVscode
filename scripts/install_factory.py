#!/usr/bin/env python3
"""Install or update Software Factory in a target repository."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

FACTORY_DIRNAME = ".copilot/softwareFactoryVscode"
DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"
DEFAULT_WORKSPACE_FILENAME = "software-factory.code-workspace"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install or update Software Factory in a target repository."
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target repository root (default: current directory)",
    )
    parser.add_argument(
        "--repo-url",
        default=DEFAULT_REPO_URL,
        help="Git repository URL or local path to clone/update from.",
    )
    parser.add_argument(
        "--ref",
        default="",
        help="Optional git branch, tag, or commit to install/update to.",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Update an existing installation instead of failing when .copilot/softwareFactoryVscode already exists.",
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
        "--skip-bootstrap",
        action="store_true",
        help="Clone/update the factory tree but do not run host bootstrap.",
    )
    parser.add_argument(
        "--skip-workspace",
        action="store_true",
        help="Pass through to bootstrap_host.py to skip workspace generation.",
    )
    parser.add_argument(
        "--force-workspace",
        action="store_true",
        help="Pass through to bootstrap_host.py to overwrite an existing custom workspace file.",
    )
    parser.add_argument(
        "--skip-gitignore",
        action="store_true",
        help="Pass through to bootstrap_host.py to skip .gitignore updates.",
    )
    return parser.parse_args(argv)


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def resolve_target_dir(target: str) -> Path:
    return Path(target).expanduser().resolve()


def validate_target_repo(target_dir: Path) -> None:
    try:
        run_command(
            ["git", "-C", str(target_dir), "rev-parse", "--is-inside-work-tree"],
            capture_output=True,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"Target path is not a git repository: {target_dir}. Run `git init` first."
        ) from exc


def ensure_clean_factory_tree(factory_dir: Path) -> None:
    status = run_command(
        ["git", "-C", str(factory_dir), "status", "--porcelain"],
        capture_output=True,
    )
    if status.stdout.strip():
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup_branch = f"local-backup-{timestamp}"
        print(
            f"⚠️  Factory installation has local changes. Backing up to branch '{backup_branch}'..."
        )
        run_command(["git", "-C", str(factory_dir), "checkout", "-b", backup_branch])
        run_command(["git", "-C", str(factory_dir), "add", "-A"])
        run_command(
            [
                "git",
                "-c",
                "user.name=Software Factory Updater",
                "-c",
                "user.email=updater@localhost",
                "-C",
                str(factory_dir),
                "commit",
                "-m",
                "Auto-backup dirty state before update",
            ]
        )

        # Switch back to the branch we were on so update_factory can reset it
        # Actually update_factory does a checkout to target_ref, so we are safe
        print(f"✅  Dirty state saved to '{backup_branch}'. Proceeding with update...")


def remote_branch_exists(factory_dir: Path, branch: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(factory_dir),
            "show-ref",
            "--verify",
            f"refs/remotes/origin/{branch}",
        ],
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def current_branch(factory_dir: Path) -> str:
    result = run_command(
        ["git", "-C", str(factory_dir), "branch", "--show-current"],
        capture_output=True,
    )
    return result.stdout.strip()


def head_commit(factory_dir: Path) -> str:
    result = run_command(
        ["git", "-C", str(factory_dir), "rev-parse", "HEAD"],
        capture_output=True,
    )
    return result.stdout.strip()


def resolve_version_label(factory_dir: Path, *, ref: str) -> str:
    normalized_ref = ref.strip()
    if normalized_ref and normalized_ref.upper() != "HEAD":
        return normalized_ref

    version_file = factory_dir / "VERSION"
    if version_file.exists():
        version = version_file.read_text(encoding="utf-8").strip()
        if version:
            return version

    return normalized_ref or current_branch(factory_dir) or "main"


def clone_factory(factory_dir: Path, *, repo_url: str, ref: str) -> None:
    run_command(["git", "clone", repo_url, str(factory_dir)])
    if ref:
        run_command(["git", "-C", str(factory_dir), "checkout", ref])


def update_factory(factory_dir: Path, *, ref: str) -> str:
    ensure_clean_factory_tree(factory_dir)
    run_command(["git", "-C", str(factory_dir), "fetch", "origin", "--prune"])
    target_ref = ref or current_branch(factory_dir) or "main"
    run_command(["git", "-C", str(factory_dir), "checkout", "-f", target_ref])

    if remote_branch_exists(factory_dir, target_ref):
        run_command(
            ["git", "-C", str(factory_dir), "reset", "--hard", f"origin/{target_ref}"]
        )

    run_command(["git", "-C", str(factory_dir), "clean", "-fd"])
    return target_ref


def invoke_bootstrap(
    *,
    target_dir: Path,
    factory_dir: Path,
    repo_url: str,
    version_label: str,
    commit_sha: str,
    workspace_file: str,
    skip_workspace: bool,
    force_workspace: bool,
    skip_gitignore: bool,
) -> None:
    bootstrap_script = factory_dir / "scripts" / "bootstrap_host.py"
    command = [
        sys.executable,
        str(bootstrap_script),
        "--target",
        str(target_dir),
        "--workspace-file",
        workspace_file,
        "--factory-version",
        version_label,
        "--factory-commit",
        commit_sha,
        "--repo-url",
        repo_url,
    ]
    if skip_workspace:
        command.append("--skip-workspace")
    if force_workspace:
        command.append("--force-workspace")
    if skip_gitignore:
        command.append("--skip-gitignore")
    run_command(command)


def invoke_verifier(
    *,
    target_dir: Path,
    factory_dir: Path,
    workspace_file: str,
    skip_workspace_check: bool,
    skip_gitignore_check: bool,
) -> None:
    verifier_script = factory_dir / "scripts" / "verify_factory_install.py"
    command = [
        sys.executable,
        str(verifier_script),
        "--target",
        str(target_dir),
        "--workspace-file",
        workspace_file,
    ]
    if skip_workspace_check:
        command.append("--skip-workspace-check")
    if skip_gitignore_check:
        command.append("--skip-gitignore-check")
    run_command(command)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir = resolve_target_dir(args.target)

    # 🧹 DESTROY EVERYTHING OF THE OLD STRUCTURE
    import shutil

    # 1. Legacy locations
    old_factory = target_dir / ".softwareFactoryVscode"
    old_tmp_dir = target_dir / ".tmp" / "softwareFactoryVscode"

    if old_factory.exists():
        print("➡️ Spinning down any running legacy factory containers before removal...")
        try:
            subprocess.run(
                [
                    sys.executable,
                    str(old_factory / "scripts" / "factory_stack.py"),
                    "stop",
                    "--repo-root",
                    str(old_factory),
                ],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            print(f"⚠️ Could not stop running legacy containers: {e}")

        print(f"🗑️  Removing legacy installation path: {old_factory}")
        shutil.rmtree(old_factory, ignore_errors=True)

    if old_tmp_dir.exists():
        print(f"🗑️  Removing legacy tmp path: {old_tmp_dir}")
        shutil.rmtree(old_tmp_dir, ignore_errors=True)

    old_env = target_dir / ".factory.env"
    if old_env.exists():
        old_env.unlink()

    factory_dir = target_dir / FACTORY_DIRNAME

    print("=================================================")
    print("📦 Installing softwareFactoryVscode")
    print("=================================================")
    print(f"Target Project: {target_dir}")
    print(f"Factory Path:   {factory_dir}")

    try:
        validate_target_repo(target_dir)

        if factory_dir.exists():
            if not args.update:
                print("⚠️ Factory is already installed at this path.")
                print("Re-run with --update to refresh the installation in place.")
                return 1

            print("➡️ Spinning down any running factory containers before update...")
            try:
                subprocess.run(
                    [
                        sys.executable,
                        str(factory_dir / "scripts" / "factory_stack.py"),
                        "stop",
                        "--repo-root",
                        str(factory_dir),
                    ],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass  # Ignore if it wasn't running or script fails

            print("➡️ Updating existing factory installation...")
            version_label = update_factory(factory_dir, ref=args.ref)
        else:
            print(f"➡️ Cloning factory repository from {args.repo_url}...")
            clone_factory(factory_dir, repo_url=args.repo_url, ref=args.ref)
            version_label = resolve_version_label(factory_dir, ref=args.ref)

        commit_sha = head_commit(factory_dir)

        print("➡️ Bootstrapping factory virtual environment (setup.sh)...")
        run_command(["bash", "setup.sh"], cwd=factory_dir)

        if args.skip_bootstrap:
            print("✅ Factory tree ready. Bootstrap skipped by request.")
            print(
                f"Next step: run {factory_dir / 'scripts' / 'bootstrap_host.py'} --target {target_dir}"
            )
            return 0

        print(
            "➡️ Bootstrapping target repository for namespace-first workspace usage..."
        )
        invoke_bootstrap(
            target_dir=target_dir,
            factory_dir=factory_dir,
            repo_url=args.repo_url,
            version_label=version_label,
            commit_sha=commit_sha,
            workspace_file=args.workspace_file,
            skip_workspace=args.skip_workspace,
            force_workspace=args.force_workspace,
            skip_gitignore=args.skip_gitignore,
        )
        print("➡️ Running post-install compliance verification...")
        invoke_verifier(
            target_dir=target_dir,
            factory_dir=factory_dir,
            workspace_file=args.workspace_file,
            skip_workspace_check=args.skip_workspace,
            skip_gitignore_check=args.skip_gitignore,
        )
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1
    except subprocess.CalledProcessError:
        print("❌ Installation failed while running git/bootstrap commands.")
        return 1

    print("✅ Factory installed successfully.")
    print(f"Open `{args.workspace_file}` in VS Code to use the installed agents.")
    print(
        "Tip: run `python3 .copilot/softwareFactoryVscode/scripts/factory_stack.py preflight` "
        "to see whether the workspace runtime is ready, needs ramp-up, or has config drift."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
