from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable

import pytest
import yaml

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    ValidationPolicy,
    ValidationPolicyError,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / CANONICAL_VALIDATION_POLICY_CONFIG_PATH


def _load_raw_policy() -> dict:
    return yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))


PolicyMutator = Callable[[dict[str, Any]], None]


def _assert_policy_error(mutator: PolicyMutator, *, match: str) -> None:
    data = copy.deepcopy(_load_raw_policy())
    mutator(data)

    with pytest.raises(ValidationPolicyError, match=match):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_missing_required_bundle_field() -> None:
    data = copy.deepcopy(_load_raw_policy())
    del data["bundles"]["docs-contract"]["summary"]

    with pytest.raises(ValidationPolicyError, match=r"bundles\.docs-contract\.summary"):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_unknown_bundle_identifier() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["official_bundle_order"] = [*data["official_bundle_order"], "shadow-bundle"]
    data["bundles"]["shadow-bundle"] = copy.deepcopy(data["bundles"]["docs-contract"])

    with pytest.raises(ValidationPolicyError, match="official_bundle_order"):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_missing_watchdog_metadata() -> None:
    data = copy.deepcopy(_load_raw_policy())
    del data["bundles"]["runtime-proofs"]["watchdog"]["timeout_kind"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.runtime-proofs\.watchdog\.timeout_kind",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_over_budget_watchdog() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["runtime-proofs"]["watchdog"]["max_minutes"] = 46

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.runtime-proofs\.watchdog\.max_minutes must be <= 45",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_unknown_watchdog_timeout_kind() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["runtime-proofs"]["watchdog"]["timeout_kind"] = "wall-clock"

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.runtime-proofs\.watchdog\.timeout_kind",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_noncanonical_authority_config_path() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["authority"]["config_path"] = "configs/shadow-validation-policy.yml"

    with pytest.raises(ValidationPolicyError, match=r"authority\.config_path"):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_noncanonical_authority_documentation_path() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["authority"]["documentation_path"] = "docs/maintainer/SHADOW-POLICY.md"

    with pytest.raises(
        ValidationPolicyError,
        match=r"authority\.documentation_path",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_malformed_bundle_metadata() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["workflow-contract"]["owner"] = "mystery-owner"

    with pytest.raises(
        ValidationPolicyError, match=r"bundles\.workflow-contract\.owner"
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_atomic_bundle_without_derivative_labels() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["docs-contract"]["current_derivative_labels"] = []

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.docs-contract\.current_derivative_labels must list at least one",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_missing_level_definition() -> None:
    data = copy.deepcopy(_load_raw_policy())
    del data["levels"]["merge"]

    with pytest.raises(ValidationPolicyError, match="Missing validation level"):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_aggregate_bundle_without_members() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["production"]["members"] = []

    with pytest.raises(ValidationPolicyError, match="Aggregate official bundles"):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_aggregate_bundle_with_self_member() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["production"]["members"] = [
        *data["bundles"]["production"]["members"],
        "production",
    ]

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.production\.members cannot include `production` itself",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_aggregate_bundle_with_non_atomic_member() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["bundles"]["production"]["members"] = ["docs-contract", "merge-full"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"bundles\.production\.members must reference only atomic bundles",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_changed_surface_rule_with_aggregate_bundle() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["changed_surface_rules"][0]["bundles"] = ["baseline"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"changed_surface_rules\[0\]\.bundles must reference only atomic",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_empty_changed_surface_rules() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["changed_surface_rules"] = []

    with pytest.raises(
        ValidationPolicyError,
        match="changed_surface_rules must not be empty",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_duplicate_changed_surface_rule_ids() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["changed_surface_rules"][1]["id"] = data["changed_surface_rules"][0]["id"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"changed_surface_rules contains duplicate ids",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_aggregate_level_with_allowed_escalations() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["levels"]["merge"]["allowed_escalations"] = ["production"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"levels\.merge\.allowed_escalations must stay empty",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_exception_with_unknown_level() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["exceptions"][0]["applies_to_levels"] = ["shadow-level"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"exceptions\[0\]\.applies_to_levels",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_exception_without_levels() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["exceptions"][0]["applies_to_levels"] = []

    with pytest.raises(
        ValidationPolicyError,
        match=r"exceptions\[0\]\.applies_to_levels must not be empty",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_empty_exceptions() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["exceptions"] = []

    with pytest.raises(
        ValidationPolicyError,
        match="exceptions must not be empty",
    ):
        ValidationPolicy.from_dict(data)


def test_validation_policy_rejects_duplicate_exception_ids() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["exceptions"][1]["id"] = data["exceptions"][0]["id"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"exceptions contains duplicate ids",
    ):
        ValidationPolicy.from_dict(data)


@pytest.mark.parametrize(
    ("mutator", "match"),
    [
        (
            lambda data: data["bundles"]["docs-contract"]["watchdog"].__setitem__(
                "max_minutes", 46
            ),
            r"bundles\.docs-contract\.watchdog\.max_minutes must be <= 45",
        ),
        (
            lambda data: data["bundles"]["docs-contract"].__setitem__(
                "members", ["workflow-contract"]
            ),
            r"bundles\.docs-contract\.members is only allowed for aggregate bundles",
        ),
        (
            lambda data: data["bundles"]["merge-full"].__setitem__(
                "members", ["baseline"]
            ),
            r"bundles\.merge-full\.members must reference only atomic bundles",
        ),
        (
            lambda data: data["levels"]["focused-local"].__setitem__(
                "default_bundle", "docs-contract"
            ),
            r"levels\.focused-local\.default_bundle must reference an aggregate official bundle",
        ),
        (
            lambda data: data["levels"]["merge"].__setitem__(
                "allowed_escalations", ["production"]
            ),
            r"levels\.merge\.allowed_escalations must stay empty for aggregate levels",
        ),
        (
            lambda data: data["changed_surface_rules"][0].__setitem__(
                "bundles", ["shadow-bundle"]
            ),
            r"changed_surface_rules\[0\]\.bundles contains unknown official bundle ids",
        ),
        (
            lambda data: data["changed_surface_rules"][0].__setitem__(
                "minimum_level", "merge"
            ),
            r"changed_surface_rules\[0\]\.minimum_level must reference a changed-surface level",
        ),
        (
            lambda data: data["changed_surface_rules"][6].__setitem__(
                "escalate_to", "baseline"
            ),
            r"changed_surface_rules\[6\]\.escalate_to must be allowed by levels\.pr-update\.allowed_escalations",
        ),
        (
            lambda data: data["changed_surface_rules"][1].__setitem__(
                "id", data["changed_surface_rules"][0]["id"]
            ),
            r"changed_surface_rules contains duplicate ids",
        ),
        (
            lambda data: data.__setitem__("exceptions", []),
            r"exceptions must not be empty once explicit policy-backed divergence is defined",
        ),
        (
            lambda data: data["exceptions"][1].__setitem__(
                "id", data["exceptions"][0]["id"]
            ),
            r"exceptions contains duplicate ids",
        ),
        (
            lambda data: data["exceptions"][0].__setitem__("summary", ""),
            r"exceptions\[0\]\.summary must be a non-empty string",
        ),
    ],
    ids=(
        "watchdog-budget-ceiling",
        "atomic-bundle-cannot-declare-members",
        "aggregate-members-must-stay-atomic",
        "changed-surface-level-default-must-stay-aggregate",
        "aggregate-level-cannot-declare-escalations",
        "rule-bundles-must-be-official",
        "rule-minimum-level-must-stay-changed-surface",
        "rule-escalation-must-be-allowed",
        "rule-ids-must-stay-unique",
        "exceptions-cannot-be-empty",
        "exception-ids-must-stay-unique",
        "exception-summary-must-be-present",
    ),
)
def test_validation_policy_rejects_broader_invalid_configs(
    mutator: PolicyMutator,
    match: str,
) -> None:
    _assert_policy_error(mutator, match=match)
