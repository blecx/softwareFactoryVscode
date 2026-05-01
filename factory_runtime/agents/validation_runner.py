"""Shared validation runner and structured reporting contract.

Issue #235 introduces the shared execution engine that consumes a resolved
official validation plan, executes the atomic bundles in that plan, and emits
one structured reporting contract for local and GitHub callers.

The runner intentionally sits below caller-specific CLI or workflow adapters.
It owns:

- execution of the official atomic bundles selected by the shared resolver;
- per-bundle watchdog/budget semantics driven by the canonical policy; and
- a structured report format with per-bundle status, timing, and terminal
  outcome information suitable for later local output, CI diagnostics, and
  watchdog-aware enforcement.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from factory_runtime.agents.validation_plan_resolver import (
    ValidationPlan,
    ValidationPlanExceptionBehavior,
    ValidationPlanReason,
)
from factory_runtime.agents.validation_policy import ValidationBundle, ValidationPolicy

DEFAULT_REPO_URL = "https://github.com/blecx/softwareFactoryVscode.git"
VALIDATION_RUN_REPORT_SCHEMA_VERSION = 1
PYTEST_FAST_FAIL_ARGS = ("-x",)
DOCS_WORKFLOW_TEST_FILES = (
    "tests/test_regression.py",
    "tests/test_todo_regression_contract.py",
    "tests/test_noninteractive_gh.py",
    "tests/test_recovery_snapshot.py",
    "tests/test_validation_policy.py",
    "tests/test_validation_policy_selection_contract.py",
    "tests/test_validation_policy_errors.py",
    "tests/test_validation_policy_docs_contract.py",
)
INSTALL_RUNTIME_TEST_FILES = (
    "tests/test_factory_install.py",
    "tests/test_workspace_surface_guard.py",
    "tests/test_runtime_mode.py",
    "tests/test_secret_safety.py",
)
RUNTIME_MANAGER_TEST_FILES = ("tests/test_mcp_runtime_manager.py",)
MULTI_TENANT_TEST_FILES = ("tests/test_multi_tenant.py",)
QUOTA_POLICY_TEST_FILES = (
    "tests/test_llm_quota_policy.py",
    "tests/test_quota_broker.py",
    "tests/test_quota_governance_contract.py",
    "tests/test_quota_load_validation.py",
)
DOCKER_E2E_TEST_FILE = "tests/test_throwaway_runtime_docker.py"
PRODUCTION_DOCKER_E2E_TEST_NAMES = (
    "strict_tenant_mode_blocks_cross_tenant_approval_leaks",
    "stop_cleanup_retains_images_and_supports_restart",
    "backup_restore_roundtrip_recovers_state_and_runtime_contract",
)
PRODUCTION_DOCKER_E2E_KEYWORD_EXPR = " or ".join(PRODUCTION_DOCKER_E2E_TEST_NAMES)
PRODUCTION_READINESS_REQUIRED_DOCS = (
    "docs/PRODUCTION-READINESS.md",
    "docs/INSTALL.md",
    "docs/CHEAT_SHEET.md",
    "docs/ops/MONITORING.md",
    "docs/ops/BACKUP-RESTORE.md",
    "docs/ops/INCIDENT-RESPONSE.md",
)
VALIDATION_STEP_STATUS_PASSED = "passed"
VALIDATION_STEP_STATUS_FAILED = "failed"
VALIDATION_STEP_STATUS_TIMED_OUT = "timed_out"
VALIDATION_STEP_STATUS_SKIPPED = "skipped"
TERMINAL_STEP_STATUSES = frozenset(
    {VALIDATION_STEP_STATUS_FAILED, VALIDATION_STEP_STATUS_TIMED_OUT}
)


class ValidationRunnerError(RuntimeError):
    """Raised when shared validation runner input or execution is invalid."""


def format_command(command: Sequence[str]) -> str:
    """Render a command exactly once for diagnostics/reporting."""

    return shlex.join(command)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _isoformat_utc(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ValidationRunnerRequest:
    """Caller-provided execution context for one resolved validation plan."""

    repo_root: Path
    plan: ValidationPlan
    base_rev: str
    head_rev: str
    python_executable: str = sys.executable
    pr_body_file: str = ""
    repo_url: str = DEFAULT_REPO_URL

    def __post_init__(self) -> None:
        normalized_repo_root = Path(self.repo_root).expanduser().resolve()
        object.__setattr__(self, "repo_root", normalized_repo_root)

        base_rev = str(self.base_rev).strip()
        if not base_rev:
            raise ValidationRunnerError("base_rev must be a non-empty revision.")
        object.__setattr__(self, "base_rev", base_rev)

        head_rev = str(self.head_rev).strip()
        if not head_rev:
            raise ValidationRunnerError("head_rev must be a non-empty revision.")
        object.__setattr__(self, "head_rev", head_rev)

        python_executable = str(self.python_executable).strip()
        if not python_executable:
            raise ValidationRunnerError(
                "python_executable must be a non-empty interpreter path."
            )
        object.__setattr__(self, "python_executable", python_executable)

        pr_body_file = str(self.pr_body_file).strip()
        if pr_body_file:
            pr_body_path = Path(pr_body_file).expanduser()
            if not pr_body_path.is_absolute():
                pr_body_path = normalized_repo_root / pr_body_path
            pr_body_file = str(pr_body_path.resolve())
        object.__setattr__(self, "pr_body_file", pr_body_file)

        repo_url = str(self.repo_url).strip()
        if not repo_url:
            raise ValidationRunnerError("repo_url must be a non-empty URL.")
        object.__setattr__(self, "repo_url", repo_url)


@dataclass(frozen=True, slots=True)
class ValidationStepReport:
    """Structured status for one concrete execution step inside a bundle."""

    step_id: str
    summary: str
    status: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    command: tuple[str, ...] = ()
    env_overrides: tuple[tuple[str, str], ...] = ()
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    failure_summary: str | None = None
    cached: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "summary": self.summary,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "command": list(self.command),
            "env_overrides": [list(item) for item in self.env_overrides],
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "failure_summary": self.failure_summary,
            "cached": self.cached,
        }


@dataclass(frozen=True, slots=True)
class ValidationBundleReport:
    """Structured execution result for one official atomic validation bundle."""

    bundle_id: str
    kind: str
    owner: str
    summary: str
    current_derivative_labels: tuple[str, ...]
    watchdog_budget_minutes: int
    timeout_kind: str
    status: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    steps: tuple[ValidationStepReport, ...]
    failure_summary: str | None = None
    skipped_reason: str | None = None

    @classmethod
    def skipped(
        cls,
        bundle: ValidationBundle,
        *,
        reason: str,
        timestamp: str,
    ) -> "ValidationBundleReport":
        return cls(
            bundle_id=bundle.bundle_id,
            kind=bundle.kind,
            owner=bundle.owner,
            summary=bundle.summary,
            current_derivative_labels=bundle.current_derivative_labels,
            watchdog_budget_minutes=bundle.watchdog.effective_budget_minutes,
            timeout_kind=bundle.watchdog.timeout_kind,
            status=VALIDATION_STEP_STATUS_SKIPPED,
            started_at=timestamp,
            completed_at=timestamp,
            elapsed_seconds=0.0,
            steps=(),
            skipped_reason=reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "kind": self.kind,
            "owner": self.owner,
            "summary": self.summary,
            "current_derivative_labels": list(self.current_derivative_labels),
            "watchdog_budget_minutes": self.watchdog_budget_minutes,
            "timeout_kind": self.timeout_kind,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "steps": [step.to_dict() for step in self.steps],
            "failure_summary": self.failure_summary,
            "skipped_reason": self.skipped_reason,
        }


@dataclass(frozen=True, slots=True)
class ValidationRunReport:
    """Structured shared-engine report for one resolved validation plan run."""

    schema_version: int
    repo_root: str
    base_rev: str
    head_rev: str
    context: str
    requested_level: str
    effective_level: str
    execution_level: str
    default_bundle: str
    resolved_bundle_ids: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]
    selected_atomic_bundles: tuple[str, ...]
    effective_atomic_bundles: tuple[str, ...]
    escalation_bundle: str | None
    applicable_exceptions: tuple[ValidationPlanExceptionBehavior, ...]
    reasons: tuple[ValidationPlanReason, ...]
    started_at: str
    completed_at: str
    elapsed_seconds: float
    terminal_outcome: str
    terminated_by_bundle_id: str | None
    bundle_reports: tuple[ValidationBundleReport, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repo_root": self.repo_root,
            "base_rev": self.base_rev,
            "head_rev": self.head_rev,
            "context": self.context,
            "requested_level": self.requested_level,
            "effective_level": self.effective_level,
            "execution_level": self.execution_level,
            "default_bundle": self.default_bundle,
            "resolved_bundle_ids": list(self.resolved_bundle_ids),
            "matched_rule_ids": list(self.matched_rule_ids),
            "selected_atomic_bundles": list(self.selected_atomic_bundles),
            "effective_atomic_bundles": list(self.effective_atomic_bundles),
            "escalation_bundle": self.escalation_bundle,
            "applicable_exceptions": [
                {
                    "exception_id": item.exception_id,
                    "summary": item.summary,
                    "applies_to_level": item.applies_to_level,
                    "context": item.context,
                    "context_behavior": item.context_behavior,
                    "rationale": item.rationale,
                }
                for item in self.applicable_exceptions
            ],
            "reasons": [
                {
                    "reason_type": item.reason_type,
                    "summary": item.summary,
                    "bundle_ids": list(item.bundle_ids),
                    "matched_paths": list(item.matched_paths),
                    "rule_id": item.rule_id,
                    "level_id": item.level_id,
                    "exception_id": item.exception_id,
                }
                for item in self.reasons
            ],
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "terminal_outcome": self.terminal_outcome,
            "terminated_by_bundle_id": self.terminated_by_bundle_id,
            "bundle_reports": [item.to_dict() for item in self.bundle_reports],
        }


CommandExecutor = Callable[
    [Sequence[str], Path, float | None, Mapping[str, str] | None],
    subprocess.CompletedProcess[str],
]
BundleExecutor = Callable[
    [ValidationRunnerRequest, ValidationBundle],
    ValidationBundleReport,
]


def _default_command_executor(
    command: Sequence[str],
    cwd: Path,
    timeout_seconds: float | None,
    env: Mapping[str, str] | None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=str(cwd),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        env=dict(env) if env is not None else None,
    )


class ValidationRunner:
    """Execute resolved official validation plans and emit structured reports."""

    def __init__(
        self,
        *,
        policy: ValidationPolicy | None = None,
        bundle_executors: Mapping[str, BundleExecutor] | None = None,
        command_executor: CommandExecutor | None = None,
        monotonic: Callable[[], float] | None = None,
        timestamp_factory: Callable[[], datetime] | None = None,
        stop_on_failure: bool = True,
    ) -> None:
        self._policy = (
            policy if policy is not None else ValidationPolicy.load_canonical()
        )
        self._command_executor = (
            command_executor
            if command_executor is not None
            else _default_command_executor
        )
        self._monotonic = monotonic if monotonic is not None else time.monotonic
        self._timestamp_factory = (
            timestamp_factory if timestamp_factory is not None else _utcnow
        )
        self._stop_on_failure = stop_on_failure
        self._shared_step_cache: dict[str, ValidationStepReport] = {}
        self._bundle_executors = dict(
            bundle_executors
            if bundle_executors is not None
            else {
                "docs-contract": self._execute_docs_contract_bundle,
                "workflow-contract": self._execute_workflow_contract_bundle,
                "install-runtime": self._execute_install_runtime_bundle,
                "runtime-manager": self._execute_runtime_manager_bundle,
                "multi-tenant": self._execute_multi_tenant_bundle,
                "quota-policy": self._execute_quota_policy_bundle,
                "integration": self._execute_integration_bundle,
                "docker-builds": self._execute_docker_builds_bundle,
                "runtime-proofs": self._execute_runtime_proofs_bundle,
            }
        )

    @property
    def registered_bundle_ids(self) -> tuple[str, ...]:
        return tuple(self._bundle_executors)

    def execute_plan(self, request: ValidationRunnerRequest) -> ValidationRunReport:
        self._shared_step_cache = {}
        plan = request.plan
        run_started_at = _isoformat_utc(self._timestamp_factory())
        run_started_monotonic = self._monotonic()
        bundle_reports: list[ValidationBundleReport] = []
        terminal_outcome = VALIDATION_STEP_STATUS_PASSED
        terminated_by_bundle_id: str | None = None

        for index, bundle_id in enumerate(plan.effective_atomic_bundles):
            bundle = self._policy.bundles.get(bundle_id)
            if bundle is None:
                raise ValidationRunnerError(
                    f"Resolved bundle `{bundle_id}` is not present in the canonical policy."
                )
            if bundle.kind != "atomic":
                raise ValidationRunnerError(
                    f"Shared runner can execute only atomic bundles, got `{bundle_id}` ({bundle.kind})."
                )

            executor = self._bundle_executors.get(bundle_id)
            if executor is None:
                raise ValidationRunnerError(
                    f"No shared runner executor is registered for official bundle `{bundle_id}`."
                )

            report = executor(request, bundle)
            bundle_reports.append(report)

            if report.status not in TERMINAL_STEP_STATUSES:
                continue

            terminal_outcome = report.status
            terminated_by_bundle_id = bundle_id
            if not self._stop_on_failure:
                continue

            skip_timestamp = report.completed_at
            for remaining_bundle_id in plan.effective_atomic_bundles[index + 1 :]:
                remaining_bundle = self._policy.bundles[remaining_bundle_id]
                bundle_reports.append(
                    ValidationBundleReport.skipped(
                        remaining_bundle,
                        reason=(
                            f"Skipped after bundle `{bundle_id}` ended the validation run "
                            f"with terminal outcome `{report.status}`."
                        ),
                        timestamp=skip_timestamp,
                    )
                )
            break

        run_completed_at = _isoformat_utc(self._timestamp_factory())
        elapsed_seconds = round(
            max(0.0, self._monotonic() - run_started_monotonic),
            6,
        )
        return ValidationRunReport(
            schema_version=VALIDATION_RUN_REPORT_SCHEMA_VERSION,
            repo_root=str(request.repo_root),
            base_rev=request.base_rev,
            head_rev=request.head_rev,
            context=plan.context,
            requested_level=plan.requested_level,
            effective_level=plan.effective_level,
            execution_level=plan.execution_level,
            default_bundle=plan.default_bundle,
            resolved_bundle_ids=plan.resolved_bundle_ids,
            matched_rule_ids=plan.matched_rule_ids,
            selected_atomic_bundles=plan.selected_atomic_bundles,
            effective_atomic_bundles=plan.effective_atomic_bundles,
            escalation_bundle=plan.escalation_bundle,
            applicable_exceptions=plan.applicable_exceptions,
            reasons=plan.reasons,
            started_at=run_started_at,
            completed_at=run_completed_at,
            elapsed_seconds=elapsed_seconds,
            terminal_outcome=terminal_outcome,
            terminated_by_bundle_id=terminated_by_bundle_id,
            bundle_reports=tuple(bundle_reports),
        )

    def _execute_docs_contract_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=(
                lambda deadline: self._execute_required_docs_step(
                    request,
                    bundle,
                    deadline,
                ),
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="release-docs-policy",
                    summary="Verify release/docs contract surfaces against the selected diff.",
                    command=(
                        request.python_executable,
                        "./scripts/verify_release_docs.py",
                        "--repo-root",
                        ".",
                        "--base-rev",
                        request.base_rev,
                        "--head-rev",
                        request.head_rev,
                    ),
                ),
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="release-manifest-parity",
                    summary="Verify release manifest parity against the canonical repo metadata.",
                    command=(
                        request.python_executable,
                        "./scripts/factory_release.py",
                        "write-manifest",
                        "--repo-root",
                        ".",
                        "--repo-url",
                        request.repo_url,
                        "--check",
                    ),
                ),
                lambda deadline: self._execute_cached_step(
                    "pytest-docs-workflow",
                    lambda: self._execute_subprocess_step(
                        request,
                        bundle,
                        deadline,
                        step_id="pytest-docs-workflow",
                        summary="Run the shared docs/workflow regression bundle.",
                        command=(
                            request.python_executable,
                            "-m",
                            "pytest",
                            *PYTEST_FAST_FAIL_ARGS,
                            *DOCS_WORKFLOW_TEST_FILES,
                        ),
                    ),
                ),
            ),
        )

    def _execute_workflow_contract_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        steps: list[Callable[[float | None], ValidationStepReport]] = [
            lambda deadline: self._execute_subprocess_step(
                request,
                bundle,
                deadline,
                step_id="git-author-identity-guard",
                summary="Reject blocked placeholder author/committer metadata before workflow handoff.",
                command=(
                    request.python_executable,
                    "./scripts/verify_git_identity.py",
                    "--repo-root",
                    ".",
                    "--head-rev",
                    request.head_rev,
                ),
            ),
            lambda deadline: self._execute_subprocess_step(
                request,
                bundle,
                deadline,
                step_id="pr-template-contract",
                summary="Validate the repository PR template against the strong-template contract.",
                command=(
                    "bash",
                    "./scripts/validate-pr-template.sh",
                    "./.github/pull_request_template.md",
                ),
            ),
        ]
        if request.pr_body_file:
            steps.append(
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="provided-pr-body-contract",
                    summary="Validate the caller-provided PR body against the PR-template contract.",
                    command=(
                        "bash",
                        "./scripts/validate-pr-template.sh",
                        request.pr_body_file,
                    ),
                )
            )
        steps.append(
            lambda deadline: self._execute_cached_step(
                "pytest-docs-workflow",
                lambda: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="pytest-docs-workflow",
                    summary="Run the shared docs/workflow regression bundle.",
                    command=(
                        request.python_executable,
                        "-m",
                        "pytest",
                        *PYTEST_FAST_FAIL_ARGS,
                        *DOCS_WORKFLOW_TEST_FILES,
                    ),
                ),
            )
        )
        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=tuple(steps),
        )

    def _execute_install_runtime_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_pytest_bundle(
            request,
            bundle,
            step_id="pytest-install-runtime",
            summary="Run install/runtime contract regressions.",
            test_files=INSTALL_RUNTIME_TEST_FILES,
        )

    def _execute_runtime_manager_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_pytest_bundle(
            request,
            bundle,
            step_id="pytest-runtime-manager",
            summary="Run runtime-manager contract regressions.",
            test_files=RUNTIME_MANAGER_TEST_FILES,
        )

    def _execute_multi_tenant_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_pytest_bundle(
            request,
            bundle,
            step_id="pytest-multi-tenant",
            summary="Run shared-tenancy and tenant-isolation regressions.",
            test_files=MULTI_TENANT_TEST_FILES,
        )

    def _execute_quota_policy_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_pytest_bundle(
            request,
            bundle,
            step_id="pytest-quota-policy",
            summary="Run quota-governance and bounded-budget regressions.",
            test_files=QUOTA_POLICY_TEST_FILES,
        )

    def _execute_integration_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=(
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="integration-boundary-regression",
                    summary="Run the repo-owned integration boundary regression.",
                    command=("bash", "./tests/run-integration-test.sh"),
                ),
            ),
        )

    def _execute_docker_builds_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        dockerfiles = sorted((request.repo_root / "docker").glob("*/Dockerfile"))
        if not dockerfiles:
            return self._execute_bundle_with_steps(
                request,
                bundle,
                steps=(
                    lambda deadline: self._failed_internal_step(
                        request,
                        bundle,
                        deadline,
                        step_id="discover-dockerfiles",
                        summary="Discover repo-owned Dockerfiles for official Docker build parity.",
                        failure_summary=(
                            "No Dockerfiles were found under `docker/*/Dockerfile`, so "
                            "official Docker build parity could not execute."
                        ),
                    ),
                ),
            )

        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=tuple(
                lambda deadline, dockerfile=dockerfile: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id=f"docker-build-{dockerfile.parent.name}",
                    summary=(
                        f"Build the repo-owned Docker image for `{dockerfile.parent.name}`."
                    ),
                    command=(
                        "docker",
                        "build",
                        "-f",
                        str(dockerfile.relative_to(request.repo_root)),
                        ".",
                        "--quiet",
                        "--tag",
                        f"factory-local-{dockerfile.parent.name}:validation-runner",
                    ),
                )
                for dockerfile in dockerfiles
            ),
        )

    def _execute_runtime_proofs_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
    ) -> ValidationBundleReport:
        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=(
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id="docker-runtime-proofs",
                    summary="Run the promoted Docker/runtime proof subset for production-grade validation evidence.",
                    command=(
                        request.python_executable,
                        "-m",
                        "pytest",
                        *PYTEST_FAST_FAIL_ARGS,
                        DOCKER_E2E_TEST_FILE,
                        "-k",
                        PRODUCTION_DOCKER_E2E_KEYWORD_EXPR,
                        "-v",
                    ),
                    env_overrides=(("RUN_DOCKER_E2E", "1"),),
                ),
            ),
        )

    def _execute_pytest_bundle(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
        *,
        step_id: str,
        summary: str,
        test_files: Sequence[str],
    ) -> ValidationBundleReport:
        return self._execute_bundle_with_steps(
            request,
            bundle,
            steps=(
                lambda deadline: self._execute_subprocess_step(
                    request,
                    bundle,
                    deadline,
                    step_id=step_id,
                    summary=summary,
                    command=(
                        request.python_executable,
                        "-m",
                        "pytest",
                        *PYTEST_FAST_FAIL_ARGS,
                        *test_files,
                    ),
                ),
            ),
        )

    def _execute_bundle_with_steps(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
        *,
        steps: Sequence[Callable[[float | None], ValidationStepReport]],
    ) -> ValidationBundleReport:
        bundle_started_at = _isoformat_utc(self._timestamp_factory())
        bundle_started_monotonic = self._monotonic()
        deadline = bundle_started_monotonic + self._bundle_budget_seconds(bundle)
        step_reports: list[ValidationStepReport] = []
        bundle_status = VALIDATION_STEP_STATUS_PASSED
        failure_summary: str | None = None

        for step in steps:
            step_report = step(deadline)
            step_reports.append(step_report)
            if step_report.status not in TERMINAL_STEP_STATUSES:
                continue
            bundle_status = step_report.status
            failure_summary = step_report.failure_summary or step_report.summary
            break

        bundle_completed_at = _isoformat_utc(self._timestamp_factory())
        elapsed_seconds = round(
            max(0.0, self._monotonic() - bundle_started_monotonic),
            6,
        )
        return ValidationBundleReport(
            bundle_id=bundle.bundle_id,
            kind=bundle.kind,
            owner=bundle.owner,
            summary=bundle.summary,
            current_derivative_labels=bundle.current_derivative_labels,
            watchdog_budget_minutes=bundle.watchdog.effective_budget_minutes,
            timeout_kind=bundle.watchdog.timeout_kind,
            status=bundle_status,
            started_at=bundle_started_at,
            completed_at=bundle_completed_at,
            elapsed_seconds=elapsed_seconds,
            steps=tuple(step_reports),
            failure_summary=failure_summary,
        )

    def _execute_cached_step(
        self,
        cache_key: str,
        step_builder: Callable[[], ValidationStepReport],
    ) -> ValidationStepReport:
        cached_report = self._shared_step_cache.get(cache_key)
        if cached_report is not None:
            return replace(cached_report, cached=True)

        report = step_builder()
        self._shared_step_cache[cache_key] = report
        return report

    def _execute_required_docs_step(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
        deadline: float | None,
    ) -> ValidationStepReport:
        timeout_seconds = self._remaining_timeout_seconds(deadline)
        if timeout_seconds is not None and timeout_seconds <= 0:
            return self._deadline_exhausted_step(
                bundle,
                step_id="required-internal-production-docs",
                summary="Verify the required internal-production docs and runbooks are present.",
            )

        started_at_dt = self._timestamp_factory()
        started_at = _isoformat_utc(started_at_dt)
        started_monotonic = self._monotonic()
        missing = [
            relative_path
            for relative_path in PRODUCTION_READINESS_REQUIRED_DOCS
            if not (request.repo_root / relative_path).is_file()
        ]

        completed_at = _isoformat_utc(self._timestamp_factory())
        elapsed_seconds = round(
            max(0.0, self._monotonic() - started_monotonic),
            6,
        )
        if not missing:
            return ValidationStepReport(
                step_id="required-internal-production-docs",
                summary="Verify the required internal-production docs and runbooks are present.",
                status=VALIDATION_STEP_STATUS_PASSED,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
            )

        failure_summary = (
            "Missing required internal-production docs/runbooks: "
            + ", ".join(f"`{path}`" for path in missing)
            + "."
        )
        return ValidationStepReport(
            step_id="required-internal-production-docs",
            summary="Verify the required internal-production docs and runbooks are present.",
            status=VALIDATION_STEP_STATUS_FAILED,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=elapsed_seconds,
            failure_summary=failure_summary,
            stderr=failure_summary,
        )

    def _failed_internal_step(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
        deadline: float | None,
        *,
        step_id: str,
        summary: str,
        failure_summary: str,
    ) -> ValidationStepReport:
        timeout_seconds = self._remaining_timeout_seconds(deadline)
        if timeout_seconds is not None and timeout_seconds <= 0:
            return self._deadline_exhausted_step(
                bundle,
                step_id=step_id,
                summary=summary,
            )

        started_at = _isoformat_utc(self._timestamp_factory())
        completed_at = _isoformat_utc(self._timestamp_factory())
        return ValidationStepReport(
            step_id=step_id,
            summary=summary,
            status=VALIDATION_STEP_STATUS_FAILED,
            started_at=started_at,
            completed_at=completed_at,
            elapsed_seconds=0.0,
            failure_summary=failure_summary,
            stderr=failure_summary,
        )

    def _execute_subprocess_step(
        self,
        request: ValidationRunnerRequest,
        bundle: ValidationBundle,
        deadline: float | None,
        *,
        step_id: str,
        summary: str,
        command: Sequence[str],
        env_overrides: tuple[tuple[str, str], ...] = (),
    ) -> ValidationStepReport:
        timeout_seconds = self._remaining_timeout_seconds(deadline)
        if timeout_seconds is not None and timeout_seconds <= 0:
            return self._deadline_exhausted_step(
                bundle,
                step_id=step_id,
                summary=summary,
                command=tuple(command),
                env_overrides=env_overrides,
            )

        started_at = _isoformat_utc(self._timestamp_factory())
        started_monotonic = self._monotonic()
        resolved_env = os.environ.copy()
        resolved_env.update(dict(env_overrides))

        try:
            result = self._command_executor(
                command,
                request.repo_root,
                timeout_seconds,
                resolved_env,
            )
            completed_at = _isoformat_utc(self._timestamp_factory())
            elapsed_seconds = round(
                max(0.0, self._monotonic() - started_monotonic),
                6,
            )
            if result.returncode == 0:
                return ValidationStepReport(
                    step_id=step_id,
                    summary=summary,
                    status=VALIDATION_STEP_STATUS_PASSED,
                    started_at=started_at,
                    completed_at=completed_at,
                    elapsed_seconds=elapsed_seconds,
                    command=tuple(command),
                    env_overrides=env_overrides,
                    returncode=result.returncode,
                    stdout=result.stdout or "",
                    stderr=result.stderr or "",
                )

            failure_summary = (
                f"{summary} failed with exit code {result.returncode}: "
                f"`{format_command(command)}`."
            )
            return ValidationStepReport(
                step_id=step_id,
                summary=summary,
                status=VALIDATION_STEP_STATUS_FAILED,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
                command=tuple(command),
                env_overrides=env_overrides,
                returncode=result.returncode,
                stdout=result.stdout or "",
                stderr=result.stderr or "",
                failure_summary=failure_summary,
            )
        except subprocess.TimeoutExpired as exc:
            completed_at = _isoformat_utc(self._timestamp_factory())
            elapsed_seconds = round(
                max(0.0, self._monotonic() - started_monotonic),
                6,
            )
            failure_summary = (
                f"{summary} exhausted the remaining bundle watchdog budget "
                f"({bundle.watchdog.effective_budget_minutes} minute(s)) while "
                f"running `{format_command(command)}`."
            )
            return ValidationStepReport(
                step_id=step_id,
                summary=summary,
                status=VALIDATION_STEP_STATUS_TIMED_OUT,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
                command=tuple(command),
                env_overrides=env_overrides,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                failure_summary=failure_summary,
            )
        except OSError as exc:
            completed_at = _isoformat_utc(self._timestamp_factory())
            elapsed_seconds = round(
                max(0.0, self._monotonic() - started_monotonic),
                6,
            )
            failure_summary = (
                f"{summary} could not start `{format_command(command)}` ({exc})."
            )
            return ValidationStepReport(
                step_id=step_id,
                summary=summary,
                status=VALIDATION_STEP_STATUS_FAILED,
                started_at=started_at,
                completed_at=completed_at,
                elapsed_seconds=elapsed_seconds,
                command=tuple(command),
                env_overrides=env_overrides,
                stderr=str(exc),
                failure_summary=failure_summary,
            )

    def _deadline_exhausted_step(
        self,
        bundle: ValidationBundle,
        *,
        step_id: str,
        summary: str,
        command: tuple[str, ...] = (),
        env_overrides: tuple[tuple[str, str], ...] = (),
    ) -> ValidationStepReport:
        timestamp = _isoformat_utc(self._timestamp_factory())
        failure_summary = (
            f"Bundle `{bundle.bundle_id}` exhausted its "
            f"{bundle.watchdog.effective_budget_minutes}-minute watchdog before "
            f"step `{step_id}` could start."
        )
        return ValidationStepReport(
            step_id=step_id,
            summary=summary,
            status=VALIDATION_STEP_STATUS_TIMED_OUT,
            started_at=timestamp,
            completed_at=timestamp,
            elapsed_seconds=0.0,
            command=command,
            env_overrides=env_overrides,
            failure_summary=failure_summary,
        )

    def _remaining_timeout_seconds(self, deadline: float | None) -> float | None:
        if deadline is None:
            return None
        return deadline - self._monotonic()

    def _bundle_budget_seconds(self, bundle: ValidationBundle) -> float:
        return float(bundle.watchdog.effective_budget_minutes * 60)
