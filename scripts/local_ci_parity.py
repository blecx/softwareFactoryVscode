#!/usr/bin/env python3
"""Run local CI-parity prechecks for softwareFactoryVscode.

This script mirrors `.github/workflows/ci.yml` checks where they are executable
locally. The default `standard` mode keeps Docker image build validation
optional for faster local iteration, while `--mode production` is the canonical
blocking parity path and includes Docker image builds plus the promoted Docker
E2E runtime proof lane by default. The existing `--include-docker-build` flag
remains available as a compatibility alias for the build-only expansion path.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"
REQUIRED_DEV_TOOL_MODULES = ("black", "flake8", "isort", "pytest")
STANDARD_MODE = "standard"
PRODUCTION_MODE = "production"
CANONICAL_PRODUCTION_PARITY_COMMAND = (
    "./.venv/bin/python ./scripts/local_ci_parity.py --mode production"
)
FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND = (
    "./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout"
)
DOCKER_BUILD_COMPATIBILITY_ALIAS = (
    "./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build"
)
PRODUCTION_GROUP_AGGREGATE = "aggregate"
PRODUCTION_GROUP_DOCS_CONTRACT = "docs-contract"
PRODUCTION_GROUP_DOCKER_BUILDS = "docker-builds"
PRODUCTION_GROUP_RUNTIME_PROOFS = "runtime-proofs"
PRODUCTION_GROUP_ORDER = (
    PRODUCTION_GROUP_DOCS_CONTRACT,
    PRODUCTION_GROUP_DOCKER_BUILDS,
    PRODUCTION_GROUP_RUNTIME_PROOFS,
)
PRODUCTION_GROUP_CHOICES = (
    PRODUCTION_GROUP_AGGREGATE,
    *PRODUCTION_GROUP_ORDER,
)
DOCKER_E2E_TEST_FILE = "tests/test_throwaway_runtime_docker.py"
PRODUCTION_READINESS_SCOPE = "internal-self-hosted-production"
PRODUCTION_READINESS_REQUIRED_GREEN_RUNS = 3
PRODUCTION_READINESS_BUNDLE_SUBDIR = Path(".tmp") / "production-readiness"
LOCAL_CI_PARITY_SNAPSHOT_PARENT_TEMPLATE = ".{repo_name}-local-ci-parity-snapshots"
DOCKER_E2E_LATEST_LOG_FILENAME = "docker-e2e-latest.log"
DOCKER_BIND_MOUNT_PARITY_LOG_FILENAME = "docker-bind-mount-parity-latest.log"
DOCKER_BIND_MOUNT_PARITY_PROBE_IMAGE = "alpine:3.22.1"
PRODUCTION_READINESS_REQUIRED_DOCS = (
    "docs/PRODUCTION-READINESS.md",
    "docs/INSTALL.md",
    "docs/CHEAT_SHEET.md",
    "docs/ops/MONITORING.md",
    "docs/ops/BACKUP-RESTORE.md",
    "docs/ops/INCIDENT-RESPONSE.md",
)
PRODUCTION_DOCKER_E2E_TEST_NAMES = (
    "strict_tenant_mode_blocks_cross_tenant_approval_leaks",
    "stop_cleanup_retains_images_and_supports_restart",
    "backup_restore_roundtrip_recovers_state_and_runtime_contract",
)
PRODUCTION_DOCKER_E2E_KEYWORD_EXPR = " or ".join(PRODUCTION_DOCKER_E2E_TEST_NAMES)
CANONICAL_PRODUCTION_DOCKER_E2E_COMMAND = (
    f"RUN_DOCKER_E2E=1 ./.venv/bin/pytest {DOCKER_E2E_TEST_FILE} "
    f'-k "{PRODUCTION_DOCKER_E2E_KEYWORD_EXPR}" -v'
)


@dataclass(frozen=True)
class StepDefinition:
    name: str
    command: tuple[str, ...]
    failure_summary: str
    remediation: str


@dataclass(frozen=True)
class Finding:
    severity: str
    name: str
    summary: str
    remediation: str
    command: tuple[str, ...] = ()
    returncode: int | None = None


@dataclass(frozen=True)
class ProductionReadinessBundle:
    run_directory: Path
    report_path: Path
    summary_path: Path
    current_green_streak: int
    required_green_runs: int
    final_signoff_status: str


def format_command(command: Sequence[str]) -> str:
    return shlex.join(command)


def docker_build_requested(args: argparse.Namespace) -> bool:
    return args.mode == PRODUCTION_MODE or args.include_docker_build


def blocking_docker_build_guidance() -> str:
    return (
        f"{CANONICAL_PRODUCTION_PARITY_COMMAND} "
        f"(or {DOCKER_BUILD_COMPATIBILITY_ALIAS})"
    )


def blocking_docker_e2e_guidance() -> str:
    return (
        f"{CANONICAL_PRODUCTION_PARITY_COMMAND} "
        f"(or {CANONICAL_PRODUCTION_DOCKER_E2E_COMMAND})"
    )


def build_rerun_command(args: argparse.Namespace) -> str:
    command: list[str] = [
        "./.venv/bin/python",
        "./scripts/local_ci_parity.py",
    ]
    if args.mode != STANDARD_MODE:
        command.extend(["--mode", args.mode])
        for group in args.production_group:
            command.extend(["--production-group", group])
    elif args.include_docker_build:
        command.append("--include-docker-build")
    if args.fresh_checkout:
        command.append("--fresh-checkout")
    if args.pr_body_file.strip():
        command.extend(["--pr-body-file", args.pr_body_file.strip()])
    if args.skip_integration:
        command.append("--skip-integration")
    if args.skip_pr_template_check:
        command.append("--skip-pr-template-check")
    if args.production_groups_only:
        command.append("--production-groups-only")
    return format_command(command)


def resolve_production_group_selection(
    args: argparse.Namespace,
) -> tuple[bool, tuple[str, ...]]:
    if args.mode != PRODUCTION_MODE and args.production_group:
        raise ValueError(
            "`--production-group` is only supported with `--mode production`."
        )

    requested = args.production_group or [PRODUCTION_GROUP_AGGREGATE]
    deduped_requested = list(dict.fromkeys(requested))

    if args.production_groups_only and args.mode != PRODUCTION_MODE:
        raise ValueError(
            "`--production-groups-only` is only supported with `--mode production`."
        )

    if PRODUCTION_GROUP_AGGREGATE in deduped_requested:
        if args.production_groups_only:
            raise ValueError(
                "`--production-groups-only` cannot be combined with aggregate "
                "production mode. Choose one or more named production groups "
                "instead."
            )
        return True, PRODUCTION_GROUP_ORDER

    selected = tuple(
        group for group in PRODUCTION_GROUP_ORDER if group in deduped_requested
    )
    return False, selected


def _current_host_posix_id(getter_name: str) -> int | None:
    getter = getattr(os, getter_name, None)
    if not callable(getter):
        return None

    try:
        return int(getter())
    except (OSError, TypeError, ValueError):
        return None


def _cleanup_docker_bind_mount_probe(
    repo_root: Path,
    *,
    probe_root: Path,
    host_uid: int | None,
    host_gid: int | None,
) -> None:
    if not probe_root.exists():
        return

    if (
        shutil.which("docker") is not None
        and host_uid is not None
        and host_gid is not None
    ):
        cleanup_command = (
            "docker",
            "run",
            "--rm",
            "-v",
            f"{probe_root}:/probe",
            DOCKER_BIND_MOUNT_PARITY_PROBE_IMAGE,
            "sh",
            "-lc",
            f"chown -R {host_uid}:{host_gid} /probe || true",
        )
        try:
            run_command(cleanup_command, cwd=repo_root)
        except OSError:
            pass

    shutil.rmtree(probe_root, ignore_errors=True)


def run_docker_bind_mount_ownership_parity_probe(repo_root: Path) -> Finding | None:
    print("\n▶ Docker bind-mount ownership parity probe")

    if shutil.which("docker") is None:
        return Finding(
            severity="error",
            name="Docker bind-mount ownership parity",
            summary=(
                "Docker CLI is required for the exact GitHub Docker-ownership parity "
                "probe but was not found on PATH."
            ),
            remediation=(
                "Install or expose the Docker CLI on PATH, then rerun "
                f"`{FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND}`."
            ),
        )

    probe_root = (
        repo_root / PRODUCTION_READINESS_BUNDLE_SUBDIR / "docker-bind-mount-parity"
    )
    transcript_path = (
        repo_root
        / PRODUCTION_READINESS_BUNDLE_SUBDIR
        / DOCKER_BIND_MOUNT_PARITY_LOG_FILENAME
    )
    nested_dir = probe_root / "nested"
    nested_file = nested_dir / "from-container"
    host_uid = _current_host_posix_id("getuid")
    host_gid = _current_host_posix_id("getgid")

    command = (
        "docker",
        "run",
        "--rm",
        "-v",
        f"{probe_root}:/probe",
        DOCKER_BIND_MOUNT_PARITY_PROBE_IMAGE,
        "sh",
        "-lc",
        (
            "mkdir -p /probe/nested && touch /probe/nested/from-container && "
            "stat -c '%u:%g %a %n' /probe/nested /probe/nested/from-container"
        ),
    )

    shutil.rmtree(probe_root, ignore_errors=True)
    probe_root.mkdir(parents=True, exist_ok=True)

    try:
        try:
            result = run_command(command, cwd=repo_root)
        except OSError as exc:
            return Finding(
                severity="error",
                name="Docker bind-mount ownership parity",
                summary=(
                    "The exact GitHub Docker-ownership parity probe could not start "
                    f"({exc})."
                ),
                remediation=(
                    "Fix the local Docker runtime environment, then rerun "
                    f"`{FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND}`."
                ),
                command=command,
            )

        write_command_transcript(
            transcript_path,
            command=command,
            result=result,
        )
        emit_command_output(result)
        if result.returncode != 0:
            return Finding(
                severity="error",
                name="Docker bind-mount ownership parity",
                summary=(
                    "The exact GitHub Docker-ownership parity probe failed to run "
                    f"(exit code {result.returncode}). Raw output was saved to "
                    f"`{display_path(transcript_path, repo_root)}`."
                ),
                remediation=(
                    "Fix the local Docker runtime environment, then rerun "
                    f"`{FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND}`."
                ),
                command=command,
                returncode=result.returncode,
            )

        if not nested_dir.exists() or not nested_file.exists():
            return Finding(
                severity="error",
                name="Docker bind-mount ownership parity",
                summary=(
                    "The exact GitHub Docker-ownership parity probe did not create the "
                    "expected nested bind-mount paths on the host."
                ),
                remediation=(
                    "Inspect the local Docker bind-mount behavior and rerun "
                    f"`{FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND}` once the probe can "
                    "observe the nested paths."
                ),
                command=command,
            )

        nested_dir_owner = (nested_dir.stat().st_uid, nested_dir.stat().st_gid)
        nested_file_owner = (nested_file.stat().st_uid, nested_file.stat().st_gid)
        nested_dir_writable = os.access(nested_dir, os.W_OK)
        nested_file_writable = os.access(nested_file, os.W_OK)

        print(
            "host_nested_dir="
            f"{nested_dir_owner[0]}:{nested_dir_owner[1]} writable={nested_dir_writable}"
        )
        print(
            "host_nested_file="
            f"{nested_file_owner[0]}:{nested_file_owner[1]} writable={nested_file_writable}"
        )

        if (
            host_uid is not None
            and host_gid is not None
            and nested_dir_owner == (host_uid, host_gid)
            and nested_file_owner == (host_uid, host_gid)
            and nested_dir_writable
            and nested_file_writable
        ):
            return Finding(
                severity="error",
                name="Docker bind-mount ownership parity",
                summary=(
                    "Local Docker bind-mount ownership semantics differ from GitHub-hosted "
                    "runners: container-root created nested bind-mount paths remain owned "
                    "and writable by the host user. Ownership-sensitive promoted Docker "
                    "proofs can pass locally while still failing remotely."
                ),
                remediation=(
                    "Run exact fresh-checkout parity on a rootful Docker daemon/context "
                    "that preserves root-owned bind-mount writes (GitHub-hosted runner "
                    "semantics), or treat GitHub CI as the source of truth for this "
                    "ownership-sensitive Docker dimension."
                ),
                command=command,
            )

        print(
            "✅ Local Docker bind-mount ownership probe did not preserve host-user "
            "ownership/writability for container-root-created nested paths."
        )
        return None
    finally:
        _cleanup_docker_bind_mount_probe(
            repo_root,
            probe_root=probe_root,
            host_uid=host_uid,
            host_gid=host_gid,
        )


def worktree_has_uncommitted_changes(repo_root: Path) -> bool:
    result = run_git(repo_root, ["status", "--short"])
    if result.returncode != 0:
        return False
    return bool(result.stdout.strip())


def create_fresh_checkout_snapshot(repo_root: Path, *, head_rev: str) -> Path:
    snapshot_parent = (
        repo_root.parent
        / LOCAL_CI_PARITY_SNAPSHOT_PARENT_TEMPLATE.format(repo_name=repo_root.name)
    )
    snapshot_parent.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    sanitized_head = (
        "".join(character for character in head_rev[:12] if character.isalnum())
        or "head"
    )
    snapshot_path = snapshot_parent / f"{timestamp}-{sanitized_head}"

    result = run_git(
        repo_root,
        ["worktree", "add", "--detach", str(snapshot_path), head_rev],
    )
    if result.returncode != 0:
        details = (
            result.stderr or result.stdout or "unknown git worktree failure"
        ).strip()
        raise RuntimeError(
            "Unable to create a fresh-checkout CI-parity snapshot via `git worktree add`: "
            f"{details}"
        )

    return snapshot_path


def build_fresh_checkout_command(
    args: argparse.Namespace,
    *,
    base_rev: str,
    head_rev: str,
) -> tuple[str, ...]:
    command: list[str] = [
        "./.venv/bin/python",
        "./scripts/local_ci_parity.py",
        "--repo-root",
        ".",
        "--base-rev",
        base_rev,
        "--head-rev",
        head_rev,
        "--python",
        "./.venv/bin/python",
    ]

    if args.mode != STANDARD_MODE:
        command.extend(["--mode", args.mode])
    elif args.include_docker_build:
        command.append("--include-docker-build")

    if args.pr_body_file.strip():
        command.extend(["--pr-body-file", args.pr_body_file.strip()])
    if args.skip_integration:
        command.append("--skip-integration")
    if args.skip_pr_template_check:
        command.append("--skip-pr-template-check")

    return tuple(command)


def run_fresh_checkout_validation(
    args: argparse.Namespace,
    *,
    repo_root: Path,
    base_rev: str,
    head_rev: str,
) -> int:
    print("\n" + "=" * 60)
    print("Fresh-checkout GitHub parity replay")
    print("=" * 60)
    print(
        "This path mirrors GitHub's clean checkout + `setup.sh` bootstrap before "
        "replaying the canonical parity command."
    )

    if args.mode == PRODUCTION_MODE:
        docker_parity_finding = run_docker_bind_mount_ownership_parity_probe(repo_root)
        if docker_parity_finding is not None:
            print_findings_report([docker_parity_finding])
            print_improvement_plan(
                [docker_parity_finding],
                rerun_command=FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND,
            )
            return 1

    if worktree_has_uncommitted_changes(repo_root):
        print(
            "ℹ️ Working tree has uncommitted changes; fresh-checkout parity replays "
            "committed HEAD only, which is the closest local match to the pushed "
            "GitHub branch state."
        )

    try:
        snapshot_path = create_fresh_checkout_snapshot(repo_root, head_rev=head_rev)
    except RuntimeError as exc:
        print(f"❌ {exc}")
        return 1

    print(f"snapshot_path={snapshot_path}")

    setup_result = run_command(("bash", "./setup.sh"), cwd=snapshot_path)
    emit_command_output(setup_result)
    if setup_result.returncode != 0:
        print(
            "❌ Fresh-checkout parity bootstrap failed during `./setup.sh`; "
            "GitHub-like validation could not start."
        )
        return 1

    child_command = build_fresh_checkout_command(
        args,
        base_rev=base_rev,
        head_rev=head_rev,
    )
    child_result = run_command(child_command, cwd=snapshot_path)
    emit_command_output(child_result)
    return child_result.returncode


def run_command(
    command: Sequence[str], *, cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
    )


def write_command_transcript(
    path: Path,
    *,
    command: Sequence[str],
    result: subprocess.CompletedProcess[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stdout = result.stdout if result.stdout else "<empty>\n"
    stderr = result.stderr if result.stderr else "<empty>\n"
    path.write_text(
        "".join(
            [
                f"Command: {format_command(command)}\n",
                f"Exit code: {result.returncode}\n",
                "\n",
                "[stdout]\n",
                stdout,
                "\n",
                "[stderr]\n",
                stderr,
            ]
        ),
        encoding="utf-8",
    )


def emit_command_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(
            result.stderr,
            file=sys.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
        )


def run_step(step: StepDefinition, *, cwd: Path) -> Finding | None:
    print(f"\n▶ {step.name}")
    try:
        result = run_command(step.command, cwd=cwd)
    except OSError as exc:
        return Finding(
            severity="error",
            name=step.name,
            summary=f"{step.failure_summary} ({exc})",
            remediation=step.remediation,
            command=step.command,
        )

    emit_command_output(result)
    if result.returncode == 0:
        return None

    return Finding(
        severity="error",
        name=step.name,
        summary=f"{step.failure_summary} (exit code {result.returncode}).",
        remediation=step.remediation,
        command=step.command,
        returncode=result.returncode,
    )


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


def build_release_contract_steps(
    args: argparse.Namespace, *, base_rev: str
) -> list[StepDefinition]:
    return [
        StepDefinition(
            name="Release docs policy check",
            command=(
                args.python,
                "./scripts/verify_release_docs.py",
                "--repo-root",
                ".",
                "--base-rev",
                base_rev,
                "--head-rev",
                args.head_rev,
            ),
            failure_summary="Release documentation policy validation failed.",
            remediation=(
                "If `VERSION` changed, update `CHANGELOG.md`, "
                "`.github/releases/v<version>.md`, and "
                "`manifests/release-manifest.json`, then rerun the precheck."
            ),
        ),
        StepDefinition(
            name="Release manifest parity check",
            command=(
                args.python,
                "./scripts/factory_release.py",
                "write-manifest",
                "--repo-root",
                ".",
                "--repo-url",
                DEFAULT_REPO_URL,
                "--check",
            ),
            failure_summary="Release manifest parity check failed.",
            remediation=(
                "Refresh `manifests/release-manifest.json` with "
                "`./scripts/factory_release.py write-manifest --repo-root . "
                f"--repo-url {DEFAULT_REPO_URL}`, review the diff, and rerun the precheck."
            ),
        ),
    ]


def build_python_quality_steps(args: argparse.Namespace) -> list[StepDefinition]:
    return [
        StepDefinition(
            name="Black format check",
            command=(
                args.python,
                "-m",
                "black",
                "--check",
                "factory_runtime/",
                "scripts/",
                "tests/",
            ),
            failure_summary="Code formatting does not match the Black profile.",
            remediation=(
                "Run Black on `factory_runtime/`, `scripts/`, and `tests/`, "
                "then review the diffs."
            ),
        ),
        StepDefinition(
            name="isort import-order check",
            command=(
                args.python,
                "-m",
                "isort",
                "--check-only",
                "factory_runtime/",
                "scripts/",
                "tests/",
            ),
            failure_summary="Import ordering does not match the isort profile.",
            remediation=(
                "Run isort on `factory_runtime/`, `scripts/`, and `tests/`, "
                "then rerun the precheck."
            ),
        ),
        StepDefinition(
            name="Flake8 lint check",
            command=(
                args.python,
                "-m",
                "flake8",
                "factory_runtime/",
                "scripts/",
                "tests/",
                "--max-line-length=120",
                "--ignore=E203,W503,E402,E731,F401,F841",
            ),
            failure_summary="Lint violations were reported by flake8.",
            remediation=(
                "Fix the reported flake8 violations in `factory_runtime/`, "
                "`scripts/`, and `tests/`, then rerun the precheck."
            ),
        ),
        StepDefinition(
            name="Pytest suite (tests/)",
            command=(args.python, "-m", "pytest", "tests/"),
            failure_summary="The pytest regression suite reported failures.",
            remediation=(
                "Investigate the failing tests under `tests/`, fix the root causes, "
                "and rerun the precheck."
            ),
        ),
    ]


def build_standard_steps(
    args: argparse.Namespace, *, base_rev: str
) -> list[StepDefinition]:
    return [
        *build_release_contract_steps(args, base_rev=base_rev),
        *build_python_quality_steps(args),
    ]


def build_python_environment_preflight_command(
    python_executable: str,
) -> tuple[str, ...]:
    return (
        python_executable,
        "-c",
        (
            "import importlib.util, json, sys; "
            "missing=[name for name in sys.argv[1:] "
            "if importlib.util.find_spec(name) is None]; "
            "print(json.dumps(missing)); "
            "raise SystemExit(1 if missing else 0)"
        ),
        *REQUIRED_DEV_TOOL_MODULES,
    )


def run_python_environment_preflight(
    python_executable: str, *, cwd: Path
) -> Finding | None:
    print("\n▶ Python environment preflight")
    command = build_python_environment_preflight_command(python_executable)

    try:
        result = run_command(command, cwd=cwd)
    except OSError as exc:
        return Finding(
            severity="error",
            name="Python environment preflight",
            summary=(
                "Python environment preflight could not start the selected "
                f"interpreter ({exc})."
            ),
            remediation=(
                "Run `./setup.sh` to install runtime and development/test "
                "dependencies into `.venv`, or point `--python` at a usable "
                "interpreter and rerun the precheck."
            ),
            command=command,
        )

    if result.stderr:
        print(
            result.stderr,
            file=sys.stderr,
            end="" if result.stderr.endswith("\n") else "\n",
        )

    missing_modules: list[str] = []
    if result.stdout.strip():
        try:
            parsed = json.loads(result.stdout)
        except json.JSONDecodeError:
            parsed = []
        if isinstance(parsed, list):
            missing_modules = [str(item) for item in parsed]

    if result.returncode == 0 and not missing_modules:
        print(
            "✅ Selected Python environment includes the required "
            "development/test modules."
        )
        return None

    if not missing_modules:
        missing_modules = list(REQUIRED_DEV_TOOL_MODULES)

    print(
        "⚠️  Missing development/test modules in the selected Python "
        f"environment: {', '.join(missing_modules)}."
    )
    return Finding(
        severity="error",
        name="Python environment preflight",
        summary=(
            "The selected Python environment is missing required "
            f"development/test modules: {', '.join(missing_modules)}."
        ),
        remediation=(
            "Run `./setup.sh` to install runtime and development/test "
            "dependencies into `.venv`, or point `--python` at an interpreter "
            "that already has `requirements.dev.txt` installed, then rerun the "
            "precheck."
        ),
        command=command,
        returncode=result.returncode or 1,
    )


def run_docker_build_validation(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    if shutil.which("docker") is None:
        findings.append(
            Finding(
                severity="error",
                name="Docker image build parity",
                summary=(
                    "Docker CLI is required for blocking Docker image build parity "
                    "but was not found on PATH."
                ),
                remediation=(
                    "Install or expose the Docker CLI on PATH, then rerun "
                    f"`{blocking_docker_build_guidance()}`."
                ),
            )
        )
        return findings

    dockerfiles = sorted((repo_root / "docker").glob("*/Dockerfile"))
    if not dockerfiles:
        findings.append(
            Finding(
                severity="error",
                name="Docker image build parity",
                summary="No Dockerfiles were found under `docker/*/Dockerfile`.",
                remediation=(
                    "Restore the expected Dockerfiles under `docker/*/Dockerfile` "
                    f"before rerunning `{blocking_docker_build_guidance()}`."
                ),
            )
        )
        return findings

    for dockerfile in dockerfiles:
        service = dockerfile.parent.name
        finding = run_step(
            StepDefinition(
                name=f"Docker build validation ({service})",
                command=(
                    "docker",
                    "build",
                    "-f",
                    str(dockerfile),
                    ".",
                    "--quiet",
                    "--tag",
                    f"factory-local-{service}:precheck",
                ),
                failure_summary=(
                    f"Docker image build validation failed for `{service}`."
                ),
                remediation=(
                    f"Inspect `docker/{service}/Dockerfile` and its repo-root build "
                    "context assumptions, then rerun "
                    f"`{blocking_docker_build_guidance()}`."
                ),
            ),
            cwd=repo_root,
        )
        if finding is not None:
            findings.append(finding)

    return findings


def run_docker_e2e_validation(
    repo_root: Path, *, python_executable: str
) -> list[Finding]:
    display_command = (
        "env",
        "RUN_DOCKER_E2E=1",
        python_executable,
        "-m",
        "pytest",
        DOCKER_E2E_TEST_FILE,
        "-k",
        PRODUCTION_DOCKER_E2E_KEYWORD_EXPR,
        "-v",
    )

    if shutil.which("docker") is None:
        return [
            Finding(
                severity="error",
                name="Docker E2E runtime proof lane",
                summary=(
                    "Docker CLI is required for the blocking Docker E2E runtime "
                    "proof lane but was not found on PATH."
                ),
                remediation=(
                    "Install or expose the Docker CLI on PATH, then rerun "
                    f"`{blocking_docker_e2e_guidance()}`."
                ),
                command=display_command,
            )
        ]

    print("\n▶ Docker E2E runtime proof lane")
    env = os.environ.copy()
    env["RUN_DOCKER_E2E"] = "1"
    command = display_command[2:]
    transcript_path = (
        repo_root / PRODUCTION_READINESS_BUNDLE_SUBDIR / DOCKER_E2E_LATEST_LOG_FILENAME
    )

    try:
        result = subprocess.run(
            list(command),
            cwd=str(repo_root),
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except OSError as exc:
        return [
            Finding(
                severity="error",
                name="Docker E2E runtime proof lane",
                summary=(
                    "The promoted Docker E2E runtime proof lane could not start "
                    f"({exc})."
                ),
                remediation=(
                    "Fix the local runtime environment, then rerun "
                    f"`{blocking_docker_e2e_guidance()}`."
                ),
                command=display_command,
            )
        ]

    write_command_transcript(
        transcript_path,
        command=display_command,
        result=result,
    )

    emit_command_output(result)
    if result.returncode == 0:
        return []

    return [
        Finding(
            severity="error",
            name="Docker E2E runtime proof lane",
            summary=(
                "The promoted Docker E2E runtime proof lane reported at least one "
                "failure among the blocking strict-tenant, stop/cleanup, and "
                "backup/restore scenarios "
                f"(exit code {result.returncode}). Raw output was saved to "
                f"`{display_path(transcript_path, repo_root)}`."
            ),
            remediation=(
                f"Investigate the promoted scenarios in `{DOCKER_E2E_TEST_FILE}` "
                f"and rerun `{blocking_docker_e2e_guidance()}` once they pass."
            ),
            command=display_command,
            returncode=result.returncode,
        )
    ]


def build_improvement_plan(
    findings: Sequence[Finding], *, rerun_command: str
) -> list[str]:
    plan: list[str] = []
    seen: set[str] = set()

    for finding in findings:
        if finding.remediation in seen:
            continue
        seen.add(finding.remediation)
        plan.append(finding.remediation)

    rerun_step = (
        f"Re-run `{rerun_command}` after applying the fixes and confirm the "
        "findings list is free of blocking errors."
    )
    if (
        any(finding.severity == "error" for finding in findings)
        and rerun_step not in seen
    ):
        plan.append(rerun_step)

    return plan


def print_findings_report(findings: Sequence[Finding]) -> None:
    print("\n" + "=" * 60)
    print("Findings")
    print("=" * 60)

    if not findings:
        print("No warnings or errors found.")
        return

    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    print(f"Summary: {error_count} error(s), {warning_count} warning(s).")

    for index, finding in enumerate(findings, start=1):
        print(f"{index}. [{finding.severity.upper()}] {finding.name}")
        print(f"   Summary: {finding.summary}")
        if finding.command:
            print(f"   Command: {format_command(finding.command)}")
        if finding.returncode is not None:
            print(f"   Exit code: {finding.returncode}")


def print_improvement_plan(findings: Sequence[Finding], *, rerun_command: str) -> None:
    plan = build_improvement_plan(findings, rerun_command=rerun_command)
    if not plan:
        return

    print("\n" + "=" * 60)
    print("Improvement plan")
    print("=" * 60)
    for index, item in enumerate(plan, start=1):
        print(f"{index}. {item}")


def run_required_documentation_validation(repo_root: Path) -> list[Finding]:
    print("\n▶ Required internal-production docs/runbooks")
    missing = [
        relative_path
        for relative_path in PRODUCTION_READINESS_REQUIRED_DOCS
        if not (repo_root / relative_path).is_file()
    ]
    if not missing:
        print(
            "✅ Required internal-production contract, operator docs, and runbooks are present."
        )
        return []

    return [
        Finding(
            severity="error",
            name="Required internal-production docs/runbooks",
            summary=(
                "Missing required internal-production docs/runbooks: "
                + ", ".join(f"`{path}`" for path in missing)
                + "."
            ),
            remediation=(
                "Restore or add the canonical internal-production contract/docs "
                "(`docs/PRODUCTION-READINESS.md`, `docs/INSTALL.md`, `docs/CHEAT_SHEET.md`, "
                "and the `docs/ops/*` runbooks) before rerunning the production gate."
            ),
        )
    ]


def resolve_head_revision(repo_root: Path, head_rev: str) -> str:
    normalized_head = head_rev.strip() or "HEAD"
    if git_ref_exists(repo_root, normalized_head):
        result = run_git(repo_root, ["rev-parse", normalized_head])
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return normalized_head


def build_default_production_readiness_history() -> dict[str, Any]:
    return {
        "required_green_runs": PRODUCTION_READINESS_REQUIRED_GREEN_RUNS,
        "current_streak": {
            "count": 0,
            "head_rev": "",
            "command": CANONICAL_PRODUCTION_PARITY_COMMAND,
        },
        "runs": [],
    }


def load_production_readiness_history(history_path: Path) -> dict[str, Any]:
    if not history_path.exists():
        return build_default_production_readiness_history()

    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return build_default_production_readiness_history()

    if not isinstance(data, dict):
        return build_default_production_readiness_history()

    return data


def write_json_file(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def display_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def build_production_readiness_summary_markdown(
    *,
    repo_root: Path,
    report_data: dict[str, Any],
) -> str:
    findings = list(report_data.get("findings", []))
    findings_lines = (
        ["- None."]
        if not findings
        else [
            "- "
            + f"**{finding['severity'].upper()}** `{finding['name']}` — {finding['summary']}"
            for finding in findings
        ]
    )

    required_docs_lines = [
        f"- `{relative_path}`" for relative_path in PRODUCTION_READINESS_REQUIRED_DOCS
    ]
    docker_e2e_lines = [
        f"- `{test_name}`" for test_name in PRODUCTION_DOCKER_E2E_TEST_NAMES
    ]

    lines = [
        "# Internal production gate — Docker parity & recovery proofs",
        "",
        f"- Scope: `{PRODUCTION_READINESS_SCOPE}`",
        f"- Gate command: `{report_data['command']}`",
        f"- Current run status: `{report_data['status']}`",
        f"- Final sign-off status: `{report_data['final_signoff_status']}`",
        (
            "- Consecutive clean runs: "
            f"`{report_data['current_green_streak']}/{report_data['required_green_runs']}`"
        ),
        f"- Head revision: `{report_data['head_rev']}`",
        f"- Base revision: `{report_data['base_rev']}`",
        "",
        "## Blocking inputs covered",
        "",
        (
            "- production-mode enforcement through the manager-backed runtime "
            "truth surfaces and production-mode regression coverage"
        ),
        "- blocking Docker image build parity for `docker/*/Dockerfile`",
        "- blocking Docker E2E runtime proof lane",
        (
            "- backup/restore roundtrip proof with runtime verification before "
            "and after restore"
        ),
        (
            "- manager-backed runtime verification including VS Code MCP "
            "endpoint checks"
        ),
        "- required internal-production docs and runbooks presence",
        "",
        "### Promoted blocking Docker E2E scenarios",
        "",
        *docker_e2e_lines,
        "",
        "## Required docs/runbooks",
        "",
        *required_docs_lines,
        "",
        "## Findings",
        "",
        *findings_lines,
        "",
        "## Bundle paths",
        "",
        (
            "- Run directory: "
            f"`{display_path(Path(report_data['run_directory']), repo_root)}`"
        ),
        (
            "- Latest JSON summary: "
            f"`{display_path(Path(report_data['latest_report_path']), repo_root)}`"
        ),
        (
            "- Latest Markdown summary: "
            f"`{display_path(Path(report_data['latest_summary_path']), repo_root)}`"
        ),
    ]
    return "\n".join(lines) + "\n"


def write_production_readiness_bundle(
    repo_root: Path,
    *,
    base_rev: str,
    head_rev: str,
    findings: Sequence[Finding],
    production_groups_executed: Sequence[str],
    production_group_results: dict[str, str],
) -> ProductionReadinessBundle:
    bundle_root = repo_root / PRODUCTION_READINESS_BUNDLE_SUBDIR
    runs_dir = bundle_root / "runs"
    history_path = bundle_root / "history.json"
    latest_report_path = bundle_root / "latest.json"
    latest_summary_path = bundle_root / "latest.md"

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    sanitized_head = (
        "".join(character for character in head_rev[:12] if character.isalnum())
        or "head"
    )
    run_directory = runs_dir / f"{timestamp}-{sanitized_head}"
    run_directory.mkdir(parents=True, exist_ok=True)

    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    green_run = error_count == 0 and warning_count == 0
    passed_run = error_count == 0

    history = load_production_readiness_history(history_path)
    current_streak = history.get("current_streak", {})
    previous_head_rev = str(current_streak.get("head_rev", "")).strip()
    previous_command = str(current_streak.get("command", "")).strip()
    previous_count = int(current_streak.get("count", 0) or 0)

    if green_run:
        if (
            previous_head_rev == head_rev
            and previous_command == CANONICAL_PRODUCTION_PARITY_COMMAND
        ):
            current_green_streak = previous_count + 1
        else:
            current_green_streak = 1
    else:
        current_green_streak = 0

    if error_count:
        final_signoff_status = "blocked"
    elif warning_count:
        final_signoff_status = "pending-clean-run"
    elif current_green_streak >= PRODUCTION_READINESS_REQUIRED_GREEN_RUNS:
        final_signoff_status = "ready"
    else:
        final_signoff_status = "pending-three-consecutive-green-runs"

    findings_payload = [
        {
            "severity": finding.severity,
            "name": finding.name,
            "summary": finding.summary,
            "remediation": finding.remediation,
            "command": list(finding.command),
            "returncode": finding.returncode,
        }
        for finding in findings
    ]

    report_data = {
        "generated_at": timestamp,
        "scope": PRODUCTION_READINESS_SCOPE,
        "command": CANONICAL_PRODUCTION_PARITY_COMMAND,
        "status": "pass" if passed_run else "fail",
        "green_run": green_run,
        "final_signoff_status": final_signoff_status,
        "required_green_runs": PRODUCTION_READINESS_REQUIRED_GREEN_RUNS,
        "current_green_streak": current_green_streak,
        "base_rev": base_rev,
        "head_rev": head_rev,
        "findings": findings_payload,
        "required_docs": list(PRODUCTION_READINESS_REQUIRED_DOCS),
        "docker_e2e_tests": list(PRODUCTION_DOCKER_E2E_TEST_NAMES),
        "production_groups_executed": list(production_groups_executed),
        "production_group_results": dict(production_group_results),
        "run_directory": str(run_directory),
        "latest_report_path": str(latest_report_path),
        "latest_summary_path": str(latest_summary_path),
    }

    report_path = run_directory / "report.json"
    summary_path = run_directory / "SUMMARY.md"
    write_json_file(report_path, report_data)
    summary_markdown = build_production_readiness_summary_markdown(
        repo_root=repo_root,
        report_data=report_data,
    )
    summary_path.write_text(summary_markdown, encoding="utf-8")
    write_json_file(latest_report_path, report_data)
    latest_summary_path.write_text(summary_markdown, encoding="utf-8")

    runs = history.get("runs", [])
    if not isinstance(runs, list):
        runs = []
    runs.append(
        {
            "generated_at": timestamp,
            "head_rev": head_rev,
            "command": CANONICAL_PRODUCTION_PARITY_COMMAND,
            "status": report_data["status"],
            "green_run": green_run,
            "final_signoff_status": final_signoff_status,
            "current_green_streak": current_green_streak,
            "run_directory": str(run_directory),
        }
    )
    history["required_green_runs"] = PRODUCTION_READINESS_REQUIRED_GREEN_RUNS
    history["current_streak"] = {
        "count": current_green_streak,
        "head_rev": head_rev,
        "command": CANONICAL_PRODUCTION_PARITY_COMMAND,
    }
    history["runs"] = runs[-20:]
    write_json_file(history_path, history)

    return ProductionReadinessBundle(
        run_directory=run_directory,
        report_path=latest_report_path,
        summary_path=latest_summary_path,
        current_green_streak=current_green_streak,
        required_green_runs=PRODUCTION_READINESS_REQUIRED_GREEN_RUNS,
        final_signoff_status=final_signoff_status,
    )


def print_production_readiness_bundle_summary(
    bundle: ProductionReadinessBundle,
    *,
    repo_root: Path,
) -> None:
    print("\n" + "=" * 60)
    print("Internal production gate sign-off — Docker parity & recovery proofs")
    print("=" * 60)
    print(f"scope={PRODUCTION_READINESS_SCOPE}")
    print(f"gate_command={CANONICAL_PRODUCTION_PARITY_COMMAND}")
    print(f"run_bundle={display_path(bundle.run_directory, repo_root)}")
    print(f"latest_report={display_path(bundle.report_path, repo_root)}")
    print(f"latest_summary={display_path(bundle.summary_path, repo_root)}")
    print(
        "current_green_streak="
        f"{bundle.current_green_streak}/{bundle.required_green_runs}"
    )
    print(f"final_signoff={bundle.final_signoff_status}")


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
        "--mode",
        choices=(STANDARD_MODE, PRODUCTION_MODE),
        default=STANDARD_MODE,
        help=(
            "Validation mode. `standard` keeps Docker build parity optional for "
            "faster local iteration; `production` is the canonical blocking parity "
            "path and includes Docker image builds plus the promoted Docker E2E "
            "runtime proof lane by default."
        ),
    )
    parser.add_argument(
        "--include-docker-build",
        action="store_true",
        help=(
            "Also run docker/*/Dockerfile build parity checks. This remains a "
            "compatibility alias for the Docker-build expansion path only when "
            "you are not using `--mode production`; it does not add the promoted "
            "Docker E2E lane."
        ),
    )
    parser.add_argument(
        "--production-group",
        action="append",
        choices=PRODUCTION_GROUP_CHOICES,
        default=[],
        help=(
            "In production mode, select one or more named production-only check "
            "groups. Defaults to `aggregate`, which runs docs-contract, "
            "docker-builds, and runtime-proofs in canonical order and emits the "
            "canonical sign-off bundle."
        ),
    )
    parser.add_argument(
        "--production-groups-only",
        action="store_true",
        help=(
            "Run only selected production groups and skip the default release, "
            "Python-quality, integration, and PR-template prechecks. Use this "
            "for production-diagnostic workflows in CI; canonical aggregate "
            "sign-off remains `--mode production` without this flag."
        ),
    )
    parser.add_argument(
        "--fresh-checkout",
        action="store_true",
        help=(
            "Replay the parity command from a clean git worktree snapshot after "
            "running `./setup.sh`, which is the closest local match to GitHub's "
            "fresh-checkout bootstrap behavior."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        aggregate_production_mode, production_groups = (
            resolve_production_group_selection(args)
        )
    except ValueError as exc:
        print(f"❌ {exc}")
        return 2

    repo_root = Path(args.repo_root).expanduser().resolve()
    head_rev = resolve_head_revision(repo_root, args.head_rev)
    base_rev = resolve_base_rev(
        repo_root,
        base_rev=args.base_rev,
        head_rev=head_rev,
    )

    if args.fresh_checkout:
        return run_fresh_checkout_validation(
            args,
            repo_root=repo_root,
            base_rev=base_rev,
            head_rev=head_rev,
        )

    print("=" * 60)
    print("Local CI-parity precheck")
    print("=" * 60)
    print(f"repo_root={repo_root}")
    print(f"base_rev={base_rev}")
    print(f"head_rev={head_rev}")
    print(f"mode={args.mode}")
    if args.mode == PRODUCTION_MODE:
        production_group_mode = (
            PRODUCTION_GROUP_AGGREGATE if aggregate_production_mode else "diagnostic"
        )
        print(
            "production_groups="
            f"{','.join(production_groups)} (mode={production_group_mode})"
        )
        if args.production_groups_only:
            print("production_groups_only=true")

    if args.mode == PRODUCTION_MODE and not os.getenv("GITHUB_ACTIONS", "").strip():
        print(
            "exact_github_parity_command=" f"{FRESH_CHECKOUT_PRODUCTION_PARITY_COMMAND}"
        )

    findings: list[Finding] = []

    if args.production_groups_only:
        print(
            "ℹ️ Skipping default prechecks because `--production-groups-only` "
            "was requested."
        )
    else:
        for step in build_release_contract_steps(args, base_rev=base_rev):
            finding = run_step(step, cwd=repo_root)
            if finding is not None:
                findings.append(finding)

        python_environment_finding = run_python_environment_preflight(
            args.python, cwd=repo_root
        )
        if python_environment_finding is not None:
            findings.append(python_environment_finding)
            print(
                "ℹ️ Skipping Python quality/test steps until the selected "
                "environment has the required development/test modules."
            )
        else:
            for step in build_python_quality_steps(args):
                finding = run_step(step, cwd=repo_root)
                if finding is not None:
                    findings.append(finding)

        if args.skip_integration:
            warning = (
                "Integration regression was skipped by request (--skip-integration)."
            )
            print(f"\nℹ️ {warning}")
            findings.append(
                Finding(
                    severity="warning",
                    name="Integration regression",
                    summary=warning,
                    remediation=(
                        "Run the standard precheck again without `--skip-integration` "
                        "before finalizing the PR."
                    ),
                    command=("bash", "./tests/run-integration-test.sh"),
                )
            )
        else:
            finding = run_step(
                StepDefinition(
                    name="Integration regression",
                    command=("bash", "./tests/run-integration-test.sh"),
                    failure_summary="The integration regression suite reported failures.",
                    remediation=(
                        "Investigate `./tests/run-integration-test.sh` failures, fix the "
                        "root cause, and rerun the precheck."
                    ),
                ),
                cwd=repo_root,
            )
            if finding is not None:
                findings.append(finding)

        if args.skip_pr_template_check:
            warning = (
                "PR-template validation was skipped by request "
                "(--skip-pr-template-check)."
            )
            print(f"ℹ️ {warning}")
            findings.append(
                Finding(
                    severity="warning",
                    name="PR-template format validation",
                    summary=warning,
                    remediation=(
                        "Run the standard precheck again without `--skip-pr-template-check` "
                        "before opening or finalizing the PR."
                    ),
                    command=(
                        "bash",
                        "./scripts/validate-pr-template.sh",
                        "./.github/pull_request_template.md",
                    ),
                )
            )
        else:
            finding = run_step(
                StepDefinition(
                    name="PR-template format validation (.github/pull_request_template.md)",
                    command=(
                        "bash",
                        "./scripts/validate-pr-template.sh",
                        "./.github/pull_request_template.md",
                    ),
                    failure_summary=(
                        "The repository PR template does not satisfy the template "
                        "validation contract."
                    ),
                    remediation=(
                        "Fix `./.github/pull_request_template.md` so it passes "
                        "`./scripts/validate-pr-template.sh`."
                    ),
                ),
                cwd=repo_root,
            )
            if finding is not None:
                findings.append(finding)
            if args.pr_body_file.strip():
                finding = run_step(
                    StepDefinition(
                        name="PR-template format validation (provided PR body)",
                        command=(
                            "bash",
                            "./scripts/validate-pr-template.sh",
                            str(Path(args.pr_body_file).expanduser().resolve()),
                        ),
                        failure_summary=(
                            "The provided PR body does not satisfy the template "
                            "validation contract."
                        ),
                        remediation=(
                            "Update the provided PR body so it passes "
                            "`./scripts/validate-pr-template.sh`."
                        ),
                    ),
                    cwd=repo_root,
                )
                if finding is not None:
                    findings.append(finding)

    docker_build_findings: list[Finding] = []
    production_group_results: dict[str, str] = {}

    if args.mode == PRODUCTION_MODE:
        for group in production_groups:
            group_findings: list[Finding] = []
            if group == PRODUCTION_GROUP_DOCS_CONTRACT:
                group_findings = run_required_documentation_validation(repo_root)
            elif group == PRODUCTION_GROUP_DOCKER_BUILDS:
                group_findings = run_docker_build_validation(repo_root)
                docker_build_findings = group_findings
            elif group == PRODUCTION_GROUP_RUNTIME_PROOFS:
                if aggregate_production_mode and any(
                    finding.severity == "error" for finding in docker_build_findings
                ):
                    print(
                        "\nℹ️ Skipping Docker E2E runtime proof lane until Docker "
                        "image build parity is green."
                    )
                    production_group_results[group] = "skipped-docker-build-errors"
                    continue
                group_findings = run_docker_e2e_validation(
                    repo_root,
                    python_executable=args.python,
                )

            findings.extend(group_findings)
            if any(finding.severity == "error" for finding in group_findings):
                production_group_results[group] = "fail"
            elif any(finding.severity == "warning" for finding in group_findings):
                production_group_results[group] = "warn"
            else:
                production_group_results[group] = "pass"

    elif docker_build_requested(args):
        docker_build_findings = run_docker_build_validation(repo_root)
        findings.extend(docker_build_findings)
    else:
        warning = (
            "Docker image build parity is skipped by default in standard mode; "
            "this run did not "
            "validate `docker/*/Dockerfile` builds."
        )
        print(
            "\nℹ️ "
            f"{warning} Run `./.venv/bin/python ./scripts/local_ci_parity.py --mode production` "
            "(or `--include-docker-build`) for blocking container-build parity."
        )
        findings.append(
            Finding(
                severity="warning",
                name="Docker image build parity",
                summary=warning,
                remediation=(
                    "Run `./.venv/bin/python ./scripts/local_ci_parity.py --mode "
                    "production` (or `--include-docker-build`) before production "
                    "sign-off when you need blocking container-build parity."
                ),
            )
        )

    print_findings_report(findings)
    print_improvement_plan(findings, rerun_command=build_rerun_command(args))

    if args.mode == PRODUCTION_MODE:
        if aggregate_production_mode:
            production_bundle = write_production_readiness_bundle(
                repo_root,
                base_rev=base_rev,
                head_rev=head_rev,
                findings=findings,
                production_groups_executed=production_groups,
                production_group_results=production_group_results,
            )
            print_production_readiness_bundle_summary(
                production_bundle,
                repo_root=repo_root,
            )
        else:
            selected_groups = ", ".join(production_groups)
            print(
                "\nℹ️ Production diagnostic-group run completed for "
                f"`{selected_groups}`. "
                "The canonical `.tmp/production-readiness/` sign-off bundle is "
                "not refreshed in diagnostic mode; run "
                f"`{CANONICAL_PRODUCTION_PARITY_COMMAND}` to refresh canonical "
                "aggregate evidence."
            )

    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")

    if error_count:
        print(
            "\n❌ Local CI-parity checks found "
            f"{error_count} error(s) and {warning_count} warning(s)."
        )
        return 1

    if warning_count:
        print(f"\n✅ Local CI-parity checks passed with {warning_count} warning(s).")
    else:
        print("\n✅ Local CI-parity checks passed with no warnings or errors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
