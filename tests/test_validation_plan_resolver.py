from __future__ import annotations

from pathlib import Path

import pytest

from factory_runtime.agents.validation_plan_resolver import (
    ValidationPlanResolverError,
    resolve_validation_plan,
)
from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    ValidationPolicy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


def test_validation_plan_resolver_keeps_bundle_plan_consistent_across_contexts() -> (
    None
):
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    local_plan = resolve_validation_plan(
        changed_paths=("configs/validation_policy.yml",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )
    github_plan = resolve_validation_plan(
        changed_paths=("configs/validation_policy.yml",),
        requested_level="focused-local",
        context="github",
        policy=policy,
    )

    assert (
        local_plan.resolved_bundle_ids
        == github_plan.resolved_bundle_ids
        == ("merge-full",)
    )
    assert local_plan.effective_atomic_bundles == github_plan.effective_atomic_bundles
    assert local_plan.execution_level == github_plan.execution_level == "merge"
    assert tuple(item.exception_id for item in local_plan.applicable_exceptions) == (
        "github-event-metadata",
        "fresh-checkout-bootstrap",
        "github-permissions-and-protected-resources",
    )
    assert tuple(item.exception_id for item in github_plan.applicable_exceptions) == (
        "github-event-metadata",
        "fresh-checkout-bootstrap",
        "github-permissions-and-protected-resources",
    )
    assert (
        local_plan.applicable_exceptions[0].context_behavior
        != github_plan.applicable_exceptions[0].context_behavior
    )


def test_validation_plan_resolver_surfaces_production_only_exception_behavior() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    local_plan = resolve_validation_plan(
        changed_paths=("docs/ops/MONITORING.md",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )

    assert local_plan.execution_level == "production"
    assert local_plan.resolved_bundle_ids == ("production",)
    assert tuple(item.exception_id for item in local_plan.applicable_exceptions) == (
        "github-event-metadata",
        "fresh-checkout-bootstrap",
        "github-permissions-and-protected-resources",
        "runner-ownership-parity",
    )
    assert (
        "bind-mount ownership probe"
        in local_plan.applicable_exceptions[-1].context_behavior
    )


def test_validation_plan_resolver_matches_recursive_directory_patterns() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    plan = resolve_validation_plan(
        changed_paths=("docker/agent-worker/Dockerfile",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )

    assert plan.effective_level == "pr-update"
    assert plan.execution_level == "production"
    assert plan.matched_rule_ids == ("production-authority-surface",)
    assert plan.selected_atomic_bundles == ("docker-builds", "runtime-proofs")
    assert plan.resolved_bundle_ids == ("production",)


def test_validation_plan_resolver_prefers_more_specific_rules_over_broad_parents() -> (
    None
):
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    plan = resolve_validation_plan(
        changed_paths=(".github/workflows/ci.yml",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )

    assert plan.effective_level == "pr-update"
    assert plan.execution_level == "merge"
    assert plan.matched_rule_ids == ("validation-contract-surface",)
    assert plan.selected_atomic_bundles == ("docs-contract", "workflow-contract")
    assert plan.resolved_bundle_ids == ("merge-full",)


def test_validation_plan_resolver_reasons_are_deterministic_and_traceable() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    plan = resolve_validation_plan(
        changed_paths=("configs/validation_policy.yml",),
        requested_level="focused-local",
        context="local",
        policy=policy,
    )

    assert tuple(reason.reason_type for reason in plan.reasons[:4]) == (
        "requested-level",
        "default-bundle",
        "matched-rule",
        "minimum-level-promotion",
    )
    matched_rule_reason = next(
        reason for reason in plan.reasons if reason.reason_type == "matched-rule"
    )
    assert matched_rule_reason.rule_id == "validation-contract-surface"
    assert matched_rule_reason.matched_paths == ("configs/validation_policy.yml",)
    assert matched_rule_reason.bundle_ids == (
        "docs-contract",
        "workflow-contract",
    )
    escalation_reason = next(
        reason for reason in plan.reasons if reason.reason_type == "escalation"
    )
    assert escalation_reason.bundle_ids == ("merge-full",)
    assert escalation_reason.level_id == "merge"


@pytest.mark.parametrize(
    ("requested_level", "context", "match"),
    [
        ("shadow-level", "local", "requested_level must be one of"),
        ("focused-local", "shadow", "context must be one of"),
    ],
)
def test_validation_plan_resolver_rejects_invalid_inputs(
    requested_level: str,
    context: str,
    match: str,
) -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    with pytest.raises(ValidationPlanResolverError, match=match):
        resolve_validation_plan(
            changed_paths=("README.md",),
            requested_level=requested_level,
            context=context,
            policy=policy,
        )
