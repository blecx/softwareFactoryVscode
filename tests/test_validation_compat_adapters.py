from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from factory_runtime.agents.validation_compat_adapters import (
    LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE,
    ValidationCompatibilityAdapterError,
    build_explicit_compatibility_plan,
    build_local_ci_production_groups_runner_request,
)
from factory_runtime.agents.validation_policy import ValidationPolicy
from factory_runtime.agents.validation_runner import (
    VALIDATION_RUN_REPORT_SCHEMA_VERSION,
    ValidationBundleReport,
    ValidationRunReport,
    ValidationStepReport,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_local_ci_parity_module():
    local_ci_path = REPO_ROOT / "scripts" / "local_ci_parity.py"
    spec = importlib.util.spec_from_file_location(
        "local_ci_parity_validation_compat_module", local_ci_path
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_local_ci_parity_documented_script_entrypoint_bootstraps_repo_imports() -> None:
    script_path = REPO_ROOT / "scripts" / "local_ci_parity.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(script_path), "--help"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Run local CI-parity checks before PR finalization." in result.stdout


def test_explicit_compatibility_plan_marks_transitional_shared_engine_surface() -> None:
    policy = ValidationPolicy.load_canonical()

    plan = build_explicit_compatibility_plan(
        bundle_ids=("docs-contract", "runtime-proofs"),
        requested_level="production",
        context="local",
        compatibility_surface=LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE,
        policy=policy,
    )

    assert plan.requested_level == "production"
    assert plan.execution_level == "production"
    assert plan.default_bundle == "production"
    assert plan.resolved_bundle_ids == ("docs-contract", "runtime-proofs")
    assert plan.selected_atomic_bundles == ("docs-contract", "runtime-proofs")
    assert plan.effective_atomic_bundles == ("docs-contract", "runtime-proofs")

    compatibility_reasons = [
        reason
        for reason in plan.reasons
        if reason.reason_type == "compatibility-adapter"
    ]
    assert len(compatibility_reasons) == 1
    assert (
        LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE
        in compatibility_reasons[0].summary
    )
    assert compatibility_reasons[0].bundle_ids == (
        "docs-contract",
        "runtime-proofs",
    )


def test_explicit_compatibility_plan_rejects_unknown_or_non_atomic_bundles() -> None:
    policy = ValidationPolicy.load_canonical()

    with pytest.raises(
        ValidationCompatibilityAdapterError, match="known official bundles"
    ):
        build_explicit_compatibility_plan(
            bundle_ids=("not-a-real-bundle",),
            requested_level="production",
            context="local",
            compatibility_surface=LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE,
            policy=policy,
        )

    with pytest.raises(
        ValidationCompatibilityAdapterError, match="official atomic bundles"
    ):
        build_explicit_compatibility_plan(
            bundle_ids=("production",),
            requested_level="production",
            context="local",
            compatibility_surface=LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE,
            policy=policy,
        )


def test_local_ci_production_groups_runner_request_preserves_revisions_and_python() -> (
    None
):
    policy = ValidationPolicy.load_canonical()

    request = build_local_ci_production_groups_runner_request(
        repo_root=REPO_ROOT,
        base_rev="base-sha",
        head_rev="head-sha",
        python_executable="/custom/python",
        selected_groups=("docker-builds",),
        policy=policy,
    )

    assert request.repo_root == REPO_ROOT
    assert request.base_rev == "base-sha"
    assert request.head_rev == "head-sha"
    assert request.python_executable == "/custom/python"
    assert request.plan.resolved_bundle_ids == ("docker-builds",)
    assert request.plan.effective_atomic_bundles == ("docker-builds",)


def test_local_ci_production_groups_only_helper_converts_runner_report_to_findings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_local_ci_parity_module()
    policy = ValidationPolicy.load_canonical()
    captured: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, *, policy):
            captured["policy"] = policy

        def execute_plan(self, request):
            captured["request"] = request
            timestamp = "2025-02-01T00:00:00Z"
            failed_step = ValidationStepReport(
                step_id="required-internal-production-docs",
                summary="Verify the required internal-production docs and runbooks are present.",
                status="failed",
                started_at=timestamp,
                completed_at=timestamp,
                elapsed_seconds=0.1,
                failure_summary=(
                    "Missing required internal-production docs/runbooks: "
                    "`docs/PRODUCTION-READINESS.md`."
                ),
                terminal_cause="internal-validation-failure",
                stderr=(
                    "Missing required internal-production docs/runbooks: "
                    "`docs/PRODUCTION-READINESS.md`."
                ),
            )
            docs_bundle = ValidationBundleReport(
                bundle_id="docs-contract",
                kind=policy.bundles["docs-contract"].kind,
                owner=policy.bundles["docs-contract"].owner,
                summary=policy.bundles["docs-contract"].summary,
                current_derivative_labels=policy.bundles[
                    "docs-contract"
                ].current_derivative_labels,
                watchdog_budget_minutes=policy.bundles[
                    "docs-contract"
                ].watchdog.effective_budget_minutes,
                timeout_kind=policy.bundles["docs-contract"].watchdog.timeout_kind,
                status="failed",
                started_at=timestamp,
                completed_at=timestamp,
                elapsed_seconds=0.1,
                steps=(failed_step,),
                failure_summary=failed_step.failure_summary,
                terminal_step_id=failed_step.step_id,
                terminal_step_summary=failed_step.summary,
                terminal_cause=failed_step.terminal_cause,
            )
            docker_bundle = ValidationBundleReport.skipped(
                policy.bundles["docker-builds"],
                reason="Skipped after `docs-contract` failed.",
                timestamp=timestamp,
            )
            return ValidationRunReport(
                schema_version=VALIDATION_RUN_REPORT_SCHEMA_VERSION,
                repo_root=str(request.repo_root),
                base_rev=request.base_rev,
                head_rev=request.head_rev,
                context=request.plan.context,
                requested_level=request.plan.requested_level,
                effective_level=request.plan.effective_level,
                execution_level=request.plan.execution_level,
                default_bundle=request.plan.default_bundle,
                resolved_bundle_ids=request.plan.resolved_bundle_ids,
                matched_rule_ids=request.plan.matched_rule_ids,
                selected_atomic_bundles=request.plan.selected_atomic_bundles,
                effective_atomic_bundles=request.plan.effective_atomic_bundles,
                escalation_bundle=request.plan.escalation_bundle,
                applicable_exceptions=request.plan.applicable_exceptions,
                reasons=request.plan.reasons,
                started_at=timestamp,
                completed_at=timestamp,
                elapsed_seconds=0.1,
                terminal_outcome="failed",
                terminated_by_bundle_id="docs-contract",
                terminal_cause="internal-validation-failure",
                bundle_reports=(docs_bundle, docker_bundle),
            )

    monkeypatch.setattr(module, "ValidationRunner", _FakeRunner)

    findings, results = module.run_selected_production_groups_via_shared_engine(
        repo_root=tmp_path,
        base_rev="base-sha",
        head_rev="head-sha",
        python_executable="/custom/python",
        selected_groups=("docs-contract", "docker-builds"),
        rerun_command=(
            "./.venv/bin/python ./scripts/local_ci_parity.py --mode production "
            "--production-group docs-contract --production-group docker-builds "
            "--production-groups-only"
        ),
    )

    request = captured["request"]
    assert request.base_rev == "base-sha"
    assert request.head_rev == "head-sha"
    assert request.python_executable == "/custom/python"
    assert request.plan.resolved_bundle_ids == ("docs-contract", "docker-builds")
    assert findings[0].name == "Required internal-production docs/runbooks"
    assert findings[0].summary.startswith("Bundle `docs-contract` ended with `failed`")
    assert "cause: `internal-validation-failure`" in findings[0].summary
    assert "Missing required internal-production docs/runbooks" in findings[0].summary
    assert "transitional compatibility adapter" in findings[0].remediation
    assert results == {
        "docs-contract": "fail",
        "docker-builds": "skipped-shared-runner-fast-fail",
    }
