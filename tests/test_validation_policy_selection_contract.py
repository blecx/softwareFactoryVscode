from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import pytest

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    ValidationPolicy,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


@dataclass(frozen=True, slots=True)
class _ResolvedSelection:
    requested_level: str
    effective_level: str
    default_bundle: str
    matched_rule_ids: tuple[str, ...]
    selected_atomic_bundles: tuple[str, ...]
    escalation_bundle: str | None


def _rule_map(policy: ValidationPolicy) -> dict[str, object]:
    return {rule.rule_id: rule for rule in policy.changed_surface_rules}


def _exception_map(policy: ValidationPolicy) -> dict[str, object]:
    return {item.exception_id: item for item in policy.exceptions}


def _matches_include_path(path: str, pattern: str) -> bool:
    normalized = str(PurePosixPath(path))
    pure_path = PurePosixPath(normalized)
    return normalized == pattern or pure_path.match(pattern)


def _resolve_selection(
    policy: ValidationPolicy,
    *,
    changed_paths: tuple[str, ...],
    requested_level: str,
) -> _ResolvedSelection:
    level = policy.levels[requested_level]
    if level.strategy == "aggregate":
        return _ResolvedSelection(
            requested_level=requested_level,
            effective_level=requested_level,
            default_bundle=level.default_bundle,
            matched_rule_ids=(),
            selected_atomic_bundles=(),
            escalation_bundle=None,
        )

    matched_rules = tuple(
        rule
        for rule in policy.changed_surface_rules
        if any(
            _matches_include_path(path, pattern)
            for path in changed_paths
            for pattern in rule.include_paths
        )
    )
    effective_level = max(
        (requested_level, *(rule.minimum_level for rule in matched_rules)),
        key=lambda level_id: policy.levels[level_id].order,
    )
    selected_atomic_bundles = tuple(
        dict.fromkeys(bundle_id for rule in matched_rules for bundle_id in rule.bundles)
    )
    escalation_candidates = tuple(
        dict.fromkeys(
            rule.escalate_to for rule in matched_rules if rule.escalate_to is not None
        )
    )
    escalation_bundle = (
        max(
            escalation_candidates,
            key=lambda bundle_id: {"merge-full": 3, "production": 4}[bundle_id],
        )
        if escalation_candidates
        else None
    )
    return _ResolvedSelection(
        requested_level=requested_level,
        effective_level=effective_level,
        default_bundle=level.default_bundle,
        matched_rule_ids=tuple(rule.rule_id for rule in matched_rules),
        selected_atomic_bundles=selected_atomic_bundles,
        escalation_bundle=escalation_bundle,
    )


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


def test_validation_policy_selection_keeps_docs_changes_in_focused_local() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    result = _resolve_selection(
        policy,
        changed_paths=("docs/README.md",),
        requested_level="focused-local",
    )

    assert result.requested_level == "focused-local"
    assert result.effective_level == "focused-local"
    assert result.default_bundle == "baseline"
    assert result.matched_rule_ids == ("docs-authority-surface",)
    assert result.selected_atomic_bundles == ("docs-contract",)
    assert result.escalation_bundle is None


def test_validation_policy_selection_promotes_integration_changes_to_pr_update() -> (
    None
):
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    result = _resolve_selection(
        policy,
        changed_paths=("compose/docker-compose.factory.yml",),
        requested_level="focused-local",
    )

    assert result.effective_level == "pr-update"
    assert result.default_bundle == "baseline"
    assert result.matched_rule_ids == ("integration-boundary-surface",)
    assert result.selected_atomic_bundles == ("integration",)
    assert result.escalation_bundle is None


def test_validation_policy_selection_escalates_contract_changes_to_merge_full() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    result = _resolve_selection(
        policy,
        changed_paths=("configs/validation_policy.yml",),
        requested_level="focused-local",
    )

    assert result.effective_level == "pr-update"
    assert result.default_bundle == "baseline"
    assert result.matched_rule_ids == ("validation-contract-surface",)
    assert result.selected_atomic_bundles == ("docs-contract", "workflow-contract")
    assert result.escalation_bundle == "merge-full"


def test_validation_policy_selection_escalates_production_surfaces_to_production() -> (
    None
):
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    result = _resolve_selection(
        policy,
        changed_paths=("docs/ops/MONITORING.md",),
        requested_level="focused-local",
    )

    assert result.effective_level == "pr-update"
    assert result.default_bundle == "baseline"
    assert result.matched_rule_ids == ("production-authority-surface",)
    assert result.selected_atomic_bundles == ("docker-builds", "runtime-proofs")
    assert result.escalation_bundle == "production"


def test_validation_policy_aggregate_levels_resolve_to_canonical_defaults() -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)

    merge_result = _resolve_selection(
        policy,
        changed_paths=("README.md",),
        requested_level="merge",
    )
    production_result = _resolve_selection(
        policy,
        changed_paths=("README.md",),
        requested_level="production",
    )

    assert merge_result.effective_level == "merge"
    assert merge_result.default_bundle == "merge-full"
    assert merge_result.matched_rule_ids == ()
    assert merge_result.selected_atomic_bundles == ()
    assert merge_result.escalation_bundle is None

    assert production_result.effective_level == "production"
    assert production_result.default_bundle == "production"
    assert production_result.matched_rule_ids == ()
    assert production_result.selected_atomic_bundles == ()
    assert production_result.escalation_bundle is None


@pytest.mark.parametrize(
    (
        "rule_id",
        "expected_paths",
        "expected_bundles",
        "expected_minimum_level",
        "expected_escalation",
    ),
    [
        (
            "docs-authority-surface",
            ("README.md", "docs/**"),
            ("docs-contract",),
            "focused-local",
            None,
        ),
        (
            "workflow-contract-surface",
            (".github/**", "scripts/validate-pr-template.sh"),
            ("workflow-contract",),
            "focused-local",
            None,
        ),
        (
            "integration-boundary-surface",
            ("compose/**", "tests/run-integration-test.sh"),
            ("integration",),
            "pr-update",
            None,
        ),
        (
            "validation-contract-surface",
            (
                "configs/validation_policy.yml",
                "factory_runtime/agents/validation_policy.py",
                "scripts/local_ci_parity.py",
            ),
            ("docs-contract", "workflow-contract"),
            "pr-update",
            "merge-full",
        ),
        (
            "production-authority-surface",
            ("docker/**", "docs/PRODUCTION-READINESS.md"),
            ("docker-builds", "runtime-proofs"),
            "pr-update",
            "production",
        ),
    ],
)
def test_validation_policy_representative_selection_scenarios_are_locked(
    rule_id: str,
    expected_paths: tuple[str, ...],
    expected_bundles: tuple[str, ...],
    expected_minimum_level: str,
    expected_escalation: str | None,
) -> None:
    policy = ValidationPolicy.from_yaml_file(POLICY_PATH)
    rule = _rule_map(policy)[rule_id]

    assert rule.bundles == expected_bundles
    assert rule.minimum_level == expected_minimum_level
    assert rule.escalate_to == expected_escalation
    for expected_path in expected_paths:
        assert expected_path in rule.include_paths


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
