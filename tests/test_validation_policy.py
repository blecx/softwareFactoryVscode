from __future__ import annotations

from pathlib import Path

from factory_runtime.agents.validation_policy import (
    CANONICAL_VALIDATION_POLICY_CONFIG_PATH,
    CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH,
    OFFICIAL_BUNDLE_ORDER,
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
    assert policy.bundles["docs-contract"].kind == "atomic"
    assert policy.bundles["production"].kind == "aggregate"
    assert policy.bundles["production"].watchdog.max_minutes == 45
    assert policy.levels == {}
    assert policy.changed_surface_rules == ()
    assert policy.exceptions == ()
