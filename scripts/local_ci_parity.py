#!/usr/bin/env python3
"""Run local CI-parity prechecks for softwareFactoryVscode.

This script mirrors `.github/workflows/ci.yml` checks where they are executable
locally. Docker image build validation is available via `--include-docker-build`
but is optional by default because it is slower and host-dependent.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"
REQUIRED_DEV_TOOL_MODULES = ("black", "flake8", "isort", "pytest")


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


def format_command(command: Sequence[str]) -> str:
    return shlex.join(command)


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
                    "Docker CLI is required for `--include-docker-build` but was "
                    "not found on PATH."
                ),
                remediation=(
                    "Install or expose the Docker CLI on PATH, then rerun the precheck "
                    "with `--include-docker-build`."
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
                    "before rerunning the precheck."
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
                    "context assumptions, then rerun the precheck with "
                    "`--include-docker-build`."
                ),
            ),
            cwd=repo_root,
        )
        if finding is not None:
            findings.append(finding)

    return findings


def build_improvement_plan(findings: Sequence[Finding]) -> list[str]:
    plan: list[str] = []
    seen: set[str] = set()

    for finding in findings:
        if finding.remediation in seen:
            continue
        seen.add(finding.remediation)
        plan.append(finding.remediation)

    rerun_step = (
        "Re-run `./.venv/bin/python ./scripts/local_ci_parity.py` after applying the "
        "fixes and confirm the findings list is free of blocking errors."
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


def print_improvement_plan(findings: Sequence[Finding]) -> None:
    plan = build_improvement_plan(findings)
    if not plan:
        return

    print("\n" + "=" * 60)
    print("Improvement plan")
    print("=" * 60)
    for index, item in enumerate(plan, start=1):
        print(f"{index}. {item}")


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

    findings: list[Finding] = []

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
        warning = "Integration regression was skipped by request (--skip-integration)."
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

    if args.include_docker_build:
        findings.extend(run_docker_build_validation(repo_root))
    else:
        warning = (
            "Docker image build parity is skipped by default; this run did not "
            "validate `docker/*/Dockerfile` builds."
        )
        print(
            "\nℹ️ "
            f"{warning} Run again with --include-docker-build for full container-build parity."
        )
        findings.append(
            Finding(
                severity="warning",
                name="Docker image build parity",
                summary=warning,
                remediation=(
                    "Run `./.venv/bin/python ./scripts/local_ci_parity.py "
                    "--include-docker-build` before merge when you need full "
                    "container-build parity."
                ),
            )
        )

    print_findings_report(findings)
    print_improvement_plan(findings)

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
