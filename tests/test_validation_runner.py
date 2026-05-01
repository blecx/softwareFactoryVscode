from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory_runtime.agents.validation_plan_resolver import resolve_validation_plan
from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    ValidationPolicy,
)
from factory_runtime.agents.validation_runner import (
    PRODUCTION_READINESS_REQUIRED_DOCS,
    VALIDATION_STEP_STATUS_FAILED,
    VALIDATION_STEP_STATUS_PASSED,
    VALIDATION_STEP_STATUS_SKIPPED,
    VALIDATION_STEP_STATUS_TIMED_OUT,
    ValidationBundleReport,
    ValidationRunner,
    ValidationRunnerRequest,
    ValidationStepReport,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


def _canonical_policy() -> ValidationPolicy:
    return ValidationPolicy.from_yaml_file(POLICY_PATH)


def _resolved_plan(*, changed_paths: tuple[str, ...], requested_level: str) -> object:
    policy = _canonical_policy()
    return resolve_validation_plan(
        changed_paths=changed_paths,
        requested_level=requested_level,
        context="local",
        policy=policy,
    )


def _write_required_docs(repo_root: Path) -> None:
    for relative_path in PRODUCTION_READINESS_REQUIRED_DOCS:
        target = repo_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {relative_path}\n", encoding="utf-8")


def test_validation_runner_executes_resolved_baseline_plan_and_emits_structured_report(
    tmp_path: Path,
) -> None:
    policy = _canonical_policy()
    plan = resolve_validation_plan(
        changed_paths=("README.md",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )
    _write_required_docs(tmp_path)
    executed_commands: list[tuple[tuple[str, ...], float | None]] = []

    def _fake_command_executor(command, cwd, timeout_seconds, env):
        del cwd, env
        executed_commands.append((tuple(command), timeout_seconds))
        return subprocess.CompletedProcess(
            list(command),
            0,
            stdout="ok\n",
            stderr="",
        )

    runner = ValidationRunner(policy=policy, command_executor=_fake_command_executor)
    report = runner.execute_plan(
        ValidationRunnerRequest(
            repo_root=tmp_path,
            plan=plan,
            base_rev="base-sha",
            head_rev="head-sha",
            python_executable=sys.executable,
        )
    )

    assert report.terminal_outcome == VALIDATION_STEP_STATUS_PASSED
    assert report.effective_atomic_bundles == ("docs-contract", "workflow-contract")
    assert tuple(item.bundle_id for item in report.bundle_reports) == (
        "docs-contract",
        "workflow-contract",
    )
    assert all(
        item.status == VALIDATION_STEP_STATUS_PASSED for item in report.bundle_reports
    )

    docs_steps = tuple(step.step_id for step in report.bundle_reports[0].steps)
    workflow_steps = tuple(step.step_id for step in report.bundle_reports[1].steps)
    assert docs_steps == (
        "required-internal-production-docs",
        "release-docs-policy",
        "release-manifest-parity",
        "pytest-docs-workflow",
    )
    assert workflow_steps == (
        "git-author-identity-guard",
        "pr-template-contract",
        "pytest-docs-workflow",
    )
    assert report.bundle_reports[1].steps[-1].cached is True

    pytest_calls = [
        command
        for command, _timeout in executed_commands
        if len(command) > 2 and command[1:3] == ("-m", "pytest")
    ]
    assert len(pytest_calls) == 1
    assert any(
        "./scripts/verify_release_docs.py" in command
        for command, _ in executed_commands
    )
    assert any(
        "./scripts/factory_release.py" in command for command, _ in executed_commands
    )
    assert any(
        "./scripts/verify_git_identity.py" in command
        for command, _ in executed_commands
    )
    assert any(
        "./scripts/validate-pr-template.sh" in command
        for command, _ in executed_commands
    )
    assert all(
        timeout is None or 0 < timeout <= 600 for _command, timeout in executed_commands
    )

    json.dumps(report.to_dict())


def test_validation_runner_times_out_and_skips_remaining_bundles(
    tmp_path: Path,
) -> None:
    policy = _canonical_policy()
    plan = resolve_validation_plan(
        changed_paths=("README.md",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )
    _write_required_docs(tmp_path)

    def _fake_command_executor(command, cwd, timeout_seconds, env):
        del cwd, env
        if len(command) > 2 and command[1:3] == ("-m", "pytest"):
            raise subprocess.TimeoutExpired(
                cmd=list(command),
                timeout=timeout_seconds or 1.0,
                output="busy\n",
                stderr="stuck\n",
            )
        return subprocess.CompletedProcess(list(command), 0, stdout="ok\n", stderr="")

    runner = ValidationRunner(policy=policy, command_executor=_fake_command_executor)
    report = runner.execute_plan(
        ValidationRunnerRequest(
            repo_root=tmp_path,
            plan=plan,
            base_rev="base-sha",
            head_rev="head-sha",
            python_executable=sys.executable,
        )
    )

    assert report.terminal_outcome == VALIDATION_STEP_STATUS_TIMED_OUT
    assert report.terminated_by_bundle_id == "docs-contract"
    assert report.bundle_reports[0].status == VALIDATION_STEP_STATUS_TIMED_OUT
    assert report.bundle_reports[0].steps[-1].status == VALIDATION_STEP_STATUS_TIMED_OUT
    assert report.bundle_reports[1].status == VALIDATION_STEP_STATUS_SKIPPED
    assert "Skipped after bundle `docs-contract`" in (
        report.bundle_reports[1].skipped_reason or ""
    )


def test_validation_runner_fast_fails_after_first_blocking_bundle_with_custom_executors(
    tmp_path: Path,
) -> None:
    policy = _canonical_policy()
    plan = resolve_validation_plan(
        changed_paths=("README.md",),
        requested_level="merge",
        context="local",
        policy=policy,
    )
    timestamp = "2026-05-01T00:00:00Z"

    def _bundle_report(bundle_id: str, status: str) -> ValidationBundleReport:
        bundle = policy.bundles[bundle_id]
        return ValidationBundleReport(
            bundle_id=bundle.bundle_id,
            kind=bundle.kind,
            owner=bundle.owner,
            summary=bundle.summary,
            current_derivative_labels=bundle.current_derivative_labels,
            watchdog_budget_minutes=bundle.watchdog.effective_budget_minutes,
            timeout_kind=bundle.watchdog.timeout_kind,
            status=status,
            started_at=timestamp,
            completed_at=timestamp,
            elapsed_seconds=0.0,
            steps=(
                ValidationStepReport(
                    step_id="synthetic-step",
                    summary="Synthetic executor output for shared runner unit coverage.",
                    status=status,
                    started_at=timestamp,
                    completed_at=timestamp,
                    elapsed_seconds=0.0,
                    failure_summary=(
                        "synthetic failure"
                        if status == VALIDATION_STEP_STATUS_FAILED
                        else None
                    ),
                ),
            ),
            failure_summary=(
                "synthetic failure" if status == VALIDATION_STEP_STATUS_FAILED else None
            ),
        )

    bundle_executors = {
        bundle_id: (
            (
                lambda request, bundle, bundle_id=bundle_id: _bundle_report(
                    bundle_id, VALIDATION_STEP_STATUS_FAILED
                )
            )
            if bundle_id == "docs-contract"
            else (
                lambda request, bundle, bundle_id=bundle_id: _bundle_report(
                    bundle_id, VALIDATION_STEP_STATUS_PASSED
                )
            )
        )
        for bundle_id, bundle in policy.bundles.items()
        if bundle.kind == "atomic"
    }

    runner = ValidationRunner(policy=policy, bundle_executors=bundle_executors)
    report = runner.execute_plan(
        ValidationRunnerRequest(
            repo_root=tmp_path,
            plan=plan,
            base_rev="base-sha",
            head_rev="head-sha",
        )
    )

    assert report.terminal_outcome == VALIDATION_STEP_STATUS_FAILED
    assert report.terminated_by_bundle_id == "docs-contract"
    assert report.bundle_reports[0].bundle_id == "docs-contract"
    assert report.bundle_reports[0].status == VALIDATION_STEP_STATUS_FAILED
    assert all(
        item.status == VALIDATION_STEP_STATUS_SKIPPED
        for item in report.bundle_reports[1:]
    )


def test_validation_runner_registers_all_official_atomic_bundle_executors() -> None:
    policy = _canonical_policy()
    runner = ValidationRunner(policy=policy)

    assert set(runner.registered_bundle_ids) == {
        bundle_id
        for bundle_id, bundle in policy.bundles.items()
        if bundle.kind == "atomic"
    }
