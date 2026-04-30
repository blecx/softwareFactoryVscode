from __future__ import annotations

from pathlib import Path

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    ValidationPolicy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


def _rule_map(policy: ValidationPolicy) -> dict[str, object]:
    return {rule.rule_id: rule for rule in policy.changed_surface_rules}


def _exception_map(policy: ValidationPolicy) -> dict[str, object]:
    return {item.exception_id: item for item in policy.exceptions}


def test_validation_policy_changed_surface_rules_cover_representative_classes() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)
    rule_map = _rule_map(policy)

    assert rule_map["docs-authority-surface"].bundles == ("docs-contract",)
    assert rule_map["workflow-contract-surface"].bundles == ("workflow-contract",)
    assert rule_map["install-runtime-surface"].bundles == ("install-runtime",)
    assert rule_map["runtime-manager-surface"].bundles == ("runtime-manager",)
    assert rule_map["quota-tenancy-surface"].bundles == (
        "multi-tenant",
        "quota-policy",
    )
    assert rule_map["integration-boundary-surface"].minimum_level == "pr-update"
    assert rule_map["validation-contract-surface"].escalate_to == "merge-full"
    assert rule_map["production-authority-surface"].escalate_to == "production"


def test_validation_policy_levels_define_explicit_escalation_boundary() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    assert policy.levels["focused-local"].strategy == "changed-surface"
    assert policy.levels["pr-update"].strategy == "changed-surface"
    assert policy.levels["focused-local"].allowed_escalations == (
        "merge-full",
        "production",
    )
    assert policy.levels["pr-update"].allowed_escalations == (
        "merge-full",
        "production",
    )
    assert policy.levels["merge"].strategy == "aggregate"
    assert policy.levels["merge"].default_bundle == "merge-full"
    assert policy.levels["production"].strategy == "aggregate"
    assert policy.levels["production"].default_bundle == "production"


def test_validation_policy_exceptions_are_explicit_and_narrow() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)
    exception_map = _exception_map(policy)

    assert tuple(exception_map) == (
        "github-event-metadata",
        "fresh-checkout-bootstrap",
        "github-permissions-and-protected-resources",
        "runner-ownership-parity",
    )
    assert exception_map["github-event-metadata"].applies_to_levels == (
        "pr-update",
        "merge",
        "production",
    )
    assert exception_map["runner-ownership-parity"].applies_to_levels == ("production",)
    assert (
        "GitHub-hosted runner"
        in exception_map["runner-ownership-parity"].github_behavior
    )
