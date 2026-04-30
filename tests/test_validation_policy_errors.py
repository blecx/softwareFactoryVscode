from __future__ import annotations

import copy
from pathlib import Path

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


def test_validation_policy_rejects_changed_surface_rule_with_aggregate_bundle() -> None:
    data = copy.deepcopy(_load_raw_policy())
    data["changed_surface_rules"][0]["bundles"] = ["baseline"]

    with pytest.raises(
        ValidationPolicyError,
        match=r"changed_surface_rules\[0\]\.bundles must reference only atomic",
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
