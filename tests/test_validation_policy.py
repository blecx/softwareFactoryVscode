from __future__ import annotations

from pathlib import Path

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH,
    OFFICIAL_BUNDLE_ORDER,
    VALIDATION_LEVEL_ORDER,
    VALIDATION_POLICY_SCHEMA_VERSION,
    ValidationPolicy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


def test_canonical_validation_policy_loads_and_preserves_official_bundle_order() -> (
    None
):
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    assert policy.schema_version == VALIDATION_POLICY_SCHEMA_VERSION
    assert policy.authority.status == "canonical"
    assert policy.authority.config_path == CANONICAL_VALIDATION_POLICY_CONFIG_PATH
    assert (
        policy.authority.documentation_path
        == CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH
    )
    assert policy.official_bundle_order == OFFICIAL_BUNDLE_ORDER
    assert tuple(policy.bundles) == OFFICIAL_BUNDLE_ORDER
    assert policy.bundles["baseline"].members == (
        "docs-contract",
        "workflow-contract",
    )
    assert policy.bundles["docs-contract"].kind == "atomic"
    assert policy.bundles["merge-full"].members == (
        "docs-contract",
        "workflow-contract",
        "install-runtime",
        "runtime-manager",
        "multi-tenant",
        "quota-policy",
        "integration",
        "docker-builds",
        "runtime-proofs",
    )
    assert policy.bundles["production"].kind == "aggregate"
    assert policy.bundles["production"].members == (
        "docs-contract",
        "docker-builds",
        "runtime-proofs",
    )
    assert policy.bundles["production"].watchdog.max_minutes == 45
    assert tuple(policy.levels) == VALIDATION_LEVEL_ORDER
    assert policy.levels["focused-local"].default_bundle == "baseline"
    assert policy.levels["merge"].default_bundle == "merge-full"
    assert policy.levels["production"].default_bundle == "production"
    assert len(policy.changed_surface_rules) == 8
    assert len(policy.exceptions) == 4


def test_canonical_validation_policy_exposes_bounded_watchdog_budget_contract() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    assert all(
        bundle.watchdog.timeout_kind == "event-driven-deadline"
        for bundle in policy.bundles.values()
    )
    assert all(
        bundle.watchdog.budget_minutes == bundle.watchdog.max_minutes
        for bundle in policy.bundles.values()
    )
    assert all(
        0 < bundle.watchdog.budget_minutes <= 45 for bundle in policy.bundles.values()
    )
    assert all(
        bundle.watchdog.effective_budget_minutes
        == min(45, bundle.watchdog.budget_minutes)
        for bundle in policy.bundles.values()
    )
    assert (
        max(
            bundle.watchdog.effective_budget_minutes
            for bundle in policy.bundles.values()
        )
        == 45
    )
