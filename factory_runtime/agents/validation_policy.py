"""Canonical validation policy contract and official bundle taxonomy.

This module owns schema validation for the repository's phase-2 validation
policy surface. It intentionally stops at bundle taxonomy and metadata for
issue #226; level composition, changed-surface selection, explicit exceptions,
and broader invalid-policy lock tests are reserved for later slices.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

VALIDATION_POLICY_SCHEMA_VERSION = 1
CANONICAL_VALIDATION_POLICY_CONFIG_PATH = "configs/validation_policy.yml"
CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH = (
    "docs/maintainer/VALIDATION-POLICY-CONTRACT.md"
)
MAX_WATCHDOG_BUDGET_MINUTES = 45
OFFICIAL_BUNDLE_ORDER = (
    "baseline",
    "docs-contract",
    "workflow-contract",
    "install-runtime",
    "runtime-manager",
    "multi-tenant",
    "quota-policy",
    "integration",
    "docker-builds",
    "runtime-proofs",
    "merge-full",
    "production",
)
OFFICIAL_BUNDLE_IDS = frozenset(OFFICIAL_BUNDLE_ORDER)
ALLOWED_BUNDLE_KINDS = frozenset({"atomic", "aggregate"})
ALLOWED_BUNDLE_OWNERS = frozenset(
    {
        "validation-contract",
        "docs",
        "workflow",
        "install-runtime",
        "runtime-manager",
        "shared-tenancy",
        "quota-governance",
        "integration",
        "docker",
    }
)
ALLOWED_TIMEOUT_KINDS = frozenset({"event-driven-deadline"})
ALLOWED_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "authority",
        "official_bundle_order",
        "bundles",
        "levels",
        "changed_surface_rules",
        "exceptions",
    }
)


class ValidationPolicyError(ValueError):
    """Raised when the canonical validation policy is malformed."""


@dataclass(frozen=True, slots=True)
class ValidationPolicyAuthority:
    """Authority metadata for the canonical validation policy surface."""

    status: str
    config_path: str
    documentation_path: str
    migration_status: str
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], *, path: str
    ) -> "ValidationPolicyAuthority":
        mapping = _expect_mapping(data, path=path)
        status = _expect_string(mapping.get("status"), path=f"{path}.status")
        if status != "canonical":
            raise ValidationPolicyError(
                f"{path}.status must be `canonical`, got `{status}`."
            )
        config_path = _expect_string(
            mapping.get("config_path"), path=f"{path}.config_path"
        )
        if config_path != CANONICAL_VALIDATION_POLICY_CONFIG_PATH:
            raise ValidationPolicyError(
                f"{path}.config_path must be `"
                f"{CANONICAL_VALIDATION_POLICY_CONFIG_PATH}` to preserve the "
                "single canonical validation policy location."
            )

        documentation_path = _expect_string(
            mapping.get("documentation_path"), path=f"{path}.documentation_path"
        )
        if documentation_path != CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH:
            raise ValidationPolicyError(
                f"{path}.documentation_path must be `"
                f"{CANONICAL_VALIDATION_POLICY_DOCUMENTATION_PATH}` to preserve the "
                "single canonical documentation authority surface."
            )

        return cls(
            status=status,
            config_path=config_path,
            documentation_path=documentation_path,
            migration_status=_expect_string(
                mapping.get("migration_status"),
                path=f"{path}.migration_status",
            ),
            notes=_expect_string_list(
                mapping.get("notes", []),
                path=f"{path}.notes",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationBundleWatchdog:
    """Bounded-runtime metadata for one official bundle."""

    max_minutes: int
    timeout_kind: str

    @classmethod
    def from_dict(
        cls, data: Mapping[str, Any], *, path: str
    ) -> "ValidationBundleWatchdog":
        mapping = _expect_mapping(data, path=path)
        max_minutes = mapping.get("max_minutes")
        if isinstance(max_minutes, bool) or not isinstance(max_minutes, int):
            raise ValidationPolicyError(
                f"{path}.max_minutes must be an integer number of minutes."
            )
        if max_minutes <= 0:
            raise ValidationPolicyError(
                f"{path}.max_minutes must be greater than 0 minutes."
            )
        if max_minutes > MAX_WATCHDOG_BUDGET_MINUTES:
            raise ValidationPolicyError(
                f"{path}.max_minutes must be <= {MAX_WATCHDOG_BUDGET_MINUTES} minutes "
                "to preserve the bounded validation contract."
            )

        timeout_kind = _expect_string(
            mapping.get("timeout_kind"),
            path=f"{path}.timeout_kind",
        )
        if timeout_kind not in ALLOWED_TIMEOUT_KINDS:
            raise ValidationPolicyError(
                f"{path}.timeout_kind must be one of "
                f"{sorted(ALLOWED_TIMEOUT_KINDS)}, got `{timeout_kind}`."
            )

        return cls(max_minutes=max_minutes, timeout_kind=timeout_kind)


@dataclass(frozen=True, slots=True)
class ValidationBundle:
    """Metadata for one official validation bundle identifier."""

    bundle_id: str
    kind: str
    owner: str
    summary: str
    current_derivative_labels: tuple[str, ...]
    watchdog: ValidationBundleWatchdog
    notes: tuple[str, ...] = ()
    members: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls,
        bundle_id: str,
        data: Mapping[str, Any],
    ) -> "ValidationBundle":
        mapping = _expect_mapping(data, path=f"bundles.{bundle_id}")
        kind = _expect_string(mapping.get("kind"), path=f"bundles.{bundle_id}.kind")
        if kind not in ALLOWED_BUNDLE_KINDS:
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.kind must be one of "
                f"{sorted(ALLOWED_BUNDLE_KINDS)}, got `{kind}`."
            )

        owner = _expect_string(mapping.get("owner"), path=f"bundles.{bundle_id}.owner")
        if owner not in ALLOWED_BUNDLE_OWNERS:
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.owner must be one of "
                f"{sorted(ALLOWED_BUNDLE_OWNERS)}, got `{owner}`."
            )

        derivative_labels = _expect_string_list(
            mapping.get("current_derivative_labels", []),
            path=f"bundles.{bundle_id}.current_derivative_labels",
            allow_empty=True,
        )
        if kind == "atomic" and not derivative_labels:
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.current_derivative_labels must list at least "
                "one current derivative label for atomic bundles."
            )

        members = _expect_string_list(
            mapping.get("members", []),
            path=f"bundles.{bundle_id}.members",
            allow_empty=True,
        )
        if kind == "atomic" and members:
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.members is only allowed for aggregate bundles."
            )

        unknown_members = [
            member for member in members if member not in OFFICIAL_BUNDLE_IDS
        ]
        if unknown_members:
            joined = ", ".join(f"`{member}`" for member in unknown_members)
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.members contains unknown official bundle ids: {joined}."
            )
        if bundle_id in members:
            raise ValidationPolicyError(
                f"bundles.{bundle_id}.members cannot include `{bundle_id}` itself."
            )

        return cls(
            bundle_id=bundle_id,
            kind=kind,
            owner=owner,
            summary=_expect_string(
                mapping.get("summary"), path=f"bundles.{bundle_id}.summary"
            ),
            current_derivative_labels=derivative_labels,
            watchdog=ValidationBundleWatchdog.from_dict(
                mapping.get("watchdog"),
                path=f"bundles.{bundle_id}.watchdog",
            ),
            notes=_expect_string_list(
                mapping.get("notes", []),
                path=f"bundles.{bundle_id}.notes",
                allow_empty=True,
            ),
            members=members,
        )


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """Canonical validation policy surface for official bundle taxonomy."""

    schema_version: int
    authority: ValidationPolicyAuthority
    official_bundle_order: tuple[str, ...]
    bundles: dict[str, ValidationBundle]
    levels: dict[str, Any]
    changed_surface_rules: tuple[dict[str, Any], ...]
    exceptions: tuple[dict[str, Any], ...]

    @classmethod
    def from_yaml_file(cls, path: Path) -> "ValidationPolicy":
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls.from_dict(data)

    @classmethod
    def load_canonical(cls) -> "ValidationPolicy":
        repo_root = Path(__file__).resolve().parents[2]
        return cls.from_yaml_file(repo_root / CANONICAL_VALIDATION_POLICY_CONFIG_PATH)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidationPolicy":
        mapping = _expect_mapping(data, path="root")
        unknown_top_level_keys = sorted(set(mapping) - ALLOWED_TOP_LEVEL_KEYS)
        if unknown_top_level_keys:
            joined = ", ".join(f"`{key}`" for key in unknown_top_level_keys)
            raise ValidationPolicyError(
                f"Unknown top-level validation policy keys: {joined}."
            )

        schema_version = mapping.get("schema_version")
        if schema_version != VALIDATION_POLICY_SCHEMA_VERSION:
            raise ValidationPolicyError(
                "Validation policy schema_version must be "
                f"`{VALIDATION_POLICY_SCHEMA_VERSION}`, got `{schema_version}`."
            )

        authority = ValidationPolicyAuthority.from_dict(
            mapping.get("authority"), path="authority"
        )
        order = _expect_string_list(
            mapping.get("official_bundle_order"),
            path="official_bundle_order",
            allow_empty=False,
        )
        if order != OFFICIAL_BUNDLE_ORDER:
            raise ValidationPolicyError(
                "official_bundle_order must exactly match the canonical official "
                f"bundle taxonomy {OFFICIAL_BUNDLE_ORDER}."
            )

        bundles_mapping = _expect_mapping(mapping.get("bundles"), path="bundles")
        unknown_bundle_ids = sorted(set(bundles_mapping) - OFFICIAL_BUNDLE_IDS)
        if unknown_bundle_ids:
            joined = ", ".join(f"`{bundle_id}`" for bundle_id in unknown_bundle_ids)
            raise ValidationPolicyError(
                f"Unknown official bundle identifiers in bundles: {joined}."
            )

        missing_bundle_ids = [
            bundle_id
            for bundle_id in OFFICIAL_BUNDLE_ORDER
            if bundle_id not in bundles_mapping
        ]
        if missing_bundle_ids:
            joined = ", ".join(f"`{bundle_id}`" for bundle_id in missing_bundle_ids)
            raise ValidationPolicyError(
                f"Missing official bundle definitions for: {joined}."
            )

        bundles = {
            bundle_id: ValidationBundle.from_dict(bundle_id, bundles_mapping[bundle_id])
            for bundle_id in OFFICIAL_BUNDLE_ORDER
        }

        levels = mapping.get("levels", {})
        if not isinstance(levels, dict):
            raise ValidationPolicyError("levels must be a mapping when present.")

        changed_surface_rules = mapping.get("changed_surface_rules", [])
        if not isinstance(changed_surface_rules, list):
            raise ValidationPolicyError(
                "changed_surface_rules must be a list when present."
            )
        normalized_changed_surface_rules = tuple(
            _expect_mapping(rule, path=f"changed_surface_rules[{index}]")
            for index, rule in enumerate(changed_surface_rules)
        )

        exceptions = mapping.get("exceptions", [])
        if not isinstance(exceptions, list):
            raise ValidationPolicyError("exceptions must be a list when present.")
        normalized_exceptions = tuple(
            _expect_mapping(item, path=f"exceptions[{index}]")
            for index, item in enumerate(exceptions)
        )

        return cls(
            schema_version=schema_version,
            authority=authority,
            official_bundle_order=order,
            bundles=bundles,
            levels=dict(levels),
            changed_surface_rules=normalized_changed_surface_rules,
            exceptions=normalized_exceptions,
        )


def _expect_mapping(value: object, *, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValidationPolicyError(f"{path} must be a mapping.")
    return value


def _expect_string(value: object, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationPolicyError(f"{path} must be a non-empty string.")
    return value.strip()


def _expect_string_list(
    value: object,
    *,
    path: str,
    allow_empty: bool,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValidationPolicyError(f"{path} must be a list of strings.")

    normalized: list[str] = []
    for index, item in enumerate(value):
        normalized.append(_expect_string(item, path=f"{path}[{index}]").strip())

    if not allow_empty and not normalized:
        raise ValidationPolicyError(f"{path} must not be empty.")

    duplicates = sorted({item for item in normalized if normalized.count(item) > 1})
    if duplicates:
        joined = ", ".join(f"`{item}`" for item in duplicates)
        raise ValidationPolicyError(f"{path} contains duplicate entries: {joined}.")

    return tuple(normalized)
