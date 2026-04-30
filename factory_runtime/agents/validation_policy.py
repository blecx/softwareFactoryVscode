"""Canonical validation policy contract and official bundle taxonomy.

This module owns schema validation for the repository's phase-2 validation
policy surface. Issue #226 established the canonical bundle taxonomy and
watchdog metadata; issue #227 extended the same surface with the four
validation levels, representative changed-surface rules, aggregate
composition, and explicit local-vs-GitHub exceptions; issue #228 locks that
contract down with the broader valid/invalid policy test suite.
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
VALIDATION_LEVEL_ORDER = (
    "focused-local",
    "pr-update",
    "merge",
    "production",
)
VALIDATION_LEVEL_IDS = frozenset(VALIDATION_LEVEL_ORDER)
ALLOWED_LEVEL_STRATEGIES = frozenset({"changed-surface", "aggregate"})
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
class ValidationLevel:
    """One canonical validation level definition."""

    level_id: str
    order: int
    summary: str
    strategy: str
    default_bundle: str
    allowed_rule_bundle_kinds: tuple[str, ...]
    allowed_escalations: tuple[str, ...]
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls,
        level_id: str,
        data: Mapping[str, Any],
        *,
        bundles: Mapping[str, ValidationBundle],
    ) -> "ValidationLevel":
        path = f"levels.{level_id}"
        mapping = _expect_mapping(data, path=path)
        order = mapping.get("order")
        if isinstance(order, bool) or not isinstance(order, int):
            raise ValidationPolicyError(f"{path}.order must be an integer.")
        if order <= 0 or order > len(VALIDATION_LEVEL_ORDER):
            raise ValidationPolicyError(
                f"{path}.order must be between 1 and {len(VALIDATION_LEVEL_ORDER)}."
            )

        strategy = _expect_string(mapping.get("strategy"), path=f"{path}.strategy")
        if strategy not in ALLOWED_LEVEL_STRATEGIES:
            raise ValidationPolicyError(
                f"{path}.strategy must be one of "
                f"{sorted(ALLOWED_LEVEL_STRATEGIES)}, got `{strategy}`."
            )

        default_bundle = _expect_string(
            mapping.get("default_bundle"), path=f"{path}.default_bundle"
        )
        if default_bundle not in OFFICIAL_BUNDLE_IDS:
            raise ValidationPolicyError(
                f"{path}.default_bundle must be one of the official bundle ids, "
                f"got `{default_bundle}`."
            )
        if bundles[default_bundle].kind != "aggregate":
            raise ValidationPolicyError(
                f"{path}.default_bundle must reference an aggregate official bundle."
            )

        allowed_rule_bundle_kinds = _expect_string_list(
            mapping.get("allowed_rule_bundle_kinds", []),
            path=f"{path}.allowed_rule_bundle_kinds",
            allow_empty=True,
        )
        invalid_rule_kinds = [
            kind
            for kind in allowed_rule_bundle_kinds
            if kind not in ALLOWED_BUNDLE_KINDS
        ]
        if invalid_rule_kinds:
            joined = ", ".join(f"`{kind}`" for kind in invalid_rule_kinds)
            raise ValidationPolicyError(
                f"{path}.allowed_rule_bundle_kinds contains invalid bundle kinds: {joined}."
            )

        allowed_escalations = _expect_string_list(
            mapping.get("allowed_escalations", []),
            path=f"{path}.allowed_escalations",
            allow_empty=True,
        )
        unknown_escalations = [
            bundle_id
            for bundle_id in allowed_escalations
            if bundle_id not in OFFICIAL_BUNDLE_IDS
        ]
        if unknown_escalations:
            joined = ", ".join(f"`{bundle_id}`" for bundle_id in unknown_escalations)
            raise ValidationPolicyError(
                f"{path}.allowed_escalations contains unknown official bundle ids: {joined}."
            )
        nonaggregate_escalations = [
            bundle_id
            for bundle_id in allowed_escalations
            if bundles[bundle_id].kind != "aggregate"
        ]
        if nonaggregate_escalations:
            joined = ", ".join(
                f"`{bundle_id}`" for bundle_id in nonaggregate_escalations
            )
            raise ValidationPolicyError(
                f"{path}.allowed_escalations must reference aggregate bundles only: {joined}."
            )

        if strategy == "aggregate":
            if allowed_rule_bundle_kinds:
                raise ValidationPolicyError(
                    f"{path}.allowed_rule_bundle_kinds must stay empty for aggregate levels."
                )
            if allowed_escalations:
                raise ValidationPolicyError(
                    f"{path}.allowed_escalations must stay empty for aggregate levels."
                )

        return cls(
            level_id=level_id,
            order=order,
            summary=_expect_string(mapping.get("summary"), path=f"{path}.summary"),
            strategy=strategy,
            default_bundle=default_bundle,
            allowed_rule_bundle_kinds=allowed_rule_bundle_kinds,
            allowed_escalations=allowed_escalations,
            notes=_expect_string_list(
                mapping.get("notes", []),
                path=f"{path}.notes",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ChangedSurfaceRule:
    """Canonical mapping from changed surfaces to official bundles."""

    rule_id: str
    summary: str
    include_paths: tuple[str, ...]
    bundles: tuple[str, ...]
    minimum_level: str
    escalate_to: str | None
    rationale: str
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        bundles: Mapping[str, ValidationBundle],
        levels: Mapping[str, ValidationLevel],
        index: int,
    ) -> "ChangedSurfaceRule":
        path = f"changed_surface_rules[{index}]"
        mapping = _expect_mapping(data, path=path)
        rule_id = _expect_string(mapping.get("id"), path=f"{path}.id")
        selected_bundles = _expect_string_list(
            mapping.get("bundles"), path=f"{path}.bundles", allow_empty=False
        )
        unknown_bundle_ids = [
            bundle_id
            for bundle_id in selected_bundles
            if bundle_id not in OFFICIAL_BUNDLE_IDS
        ]
        if unknown_bundle_ids:
            joined = ", ".join(f"`{bundle_id}`" for bundle_id in unknown_bundle_ids)
            raise ValidationPolicyError(
                f"{path}.bundles contains unknown official bundle ids: {joined}."
            )
        non_atomic_bundles = [
            bundle_id
            for bundle_id in selected_bundles
            if bundles[bundle_id].kind != "atomic"
        ]
        if non_atomic_bundles:
            joined = ", ".join(f"`{bundle_id}`" for bundle_id in non_atomic_bundles)
            raise ValidationPolicyError(
                f"{path}.bundles must reference only atomic official bundles: {joined}."
            )

        minimum_level = _expect_string(
            mapping.get("minimum_level"), path=f"{path}.minimum_level"
        )
        if minimum_level not in VALIDATION_LEVEL_IDS:
            raise ValidationPolicyError(
                f"{path}.minimum_level must be one of {VALIDATION_LEVEL_ORDER}, got `{minimum_level}`."
            )
        if levels[minimum_level].strategy != "changed-surface":
            raise ValidationPolicyError(
                f"{path}.minimum_level must reference a changed-surface level."
            )

        raw_escalation = mapping.get("escalate_to")
        escalate_to: str | None
        if raw_escalation is None:
            escalate_to = None
        else:
            escalate_to = _expect_string(raw_escalation, path=f"{path}.escalate_to")
            if escalate_to not in OFFICIAL_BUNDLE_IDS:
                raise ValidationPolicyError(
                    f"{path}.escalate_to must be an official bundle id, got `{escalate_to}`."
                )
            if bundles[escalate_to].kind != "aggregate":
                raise ValidationPolicyError(
                    f"{path}.escalate_to must reference an aggregate bundle."
                )
            if escalate_to not in levels[minimum_level].allowed_escalations:
                raise ValidationPolicyError(
                    f"{path}.escalate_to must be allowed by levels.{minimum_level}.allowed_escalations."
                )

        return cls(
            rule_id=rule_id,
            summary=_expect_string(mapping.get("summary"), path=f"{path}.summary"),
            include_paths=_expect_string_list(
                mapping.get("include_paths"),
                path=f"{path}.include_paths",
                allow_empty=False,
            ),
            bundles=selected_bundles,
            minimum_level=minimum_level,
            escalate_to=escalate_to,
            rationale=_expect_string(
                mapping.get("rationale"), path=f"{path}.rationale"
            ),
            notes=_expect_string_list(
                mapping.get("notes", []),
                path=f"{path}.notes",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationPolicyException:
    """Explicit allowed local-vs-GitHub validation divergence."""

    exception_id: str
    applies_to_levels: tuple[str, ...]
    summary: str
    local_behavior: str
    github_behavior: str
    rationale: str
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        index: int,
    ) -> "ValidationPolicyException":
        path = f"exceptions[{index}]"
        mapping = _expect_mapping(data, path=path)
        applies_to_levels = _expect_string_list(
            mapping.get("applies_to_levels"),
            path=f"{path}.applies_to_levels",
            allow_empty=False,
        )
        unknown_levels = [
            level_id
            for level_id in applies_to_levels
            if level_id not in VALIDATION_LEVEL_IDS
        ]
        if unknown_levels:
            joined = ", ".join(f"`{level_id}`" for level_id in unknown_levels)
            raise ValidationPolicyError(
                f"{path}.applies_to_levels contains unknown validation levels: {joined}."
            )

        return cls(
            exception_id=_expect_string(mapping.get("id"), path=f"{path}.id"),
            applies_to_levels=applies_to_levels,
            summary=_expect_string(mapping.get("summary"), path=f"{path}.summary"),
            local_behavior=_expect_string(
                mapping.get("local_behavior"), path=f"{path}.local_behavior"
            ),
            github_behavior=_expect_string(
                mapping.get("github_behavior"), path=f"{path}.github_behavior"
            ),
            rationale=_expect_string(
                mapping.get("rationale"), path=f"{path}.rationale"
            ),
            notes=_expect_string_list(
                mapping.get("notes", []),
                path=f"{path}.notes",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ValidationPolicy:
    """Canonical validation policy surface for official bundle taxonomy."""

    schema_version: int
    authority: ValidationPolicyAuthority
    official_bundle_order: tuple[str, ...]
    bundles: dict[str, ValidationBundle]
    levels: dict[str, ValidationLevel]
    changed_surface_rules: tuple[ChangedSurfaceRule, ...]
    exceptions: tuple[ValidationPolicyException, ...]

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

        aggregate_bundle_ids = [
            bundle_id
            for bundle_id, bundle in bundles.items()
            if bundle.kind == "aggregate"
        ]
        missing_aggregate_members = [
            bundle_id
            for bundle_id in aggregate_bundle_ids
            if not bundles[bundle_id].members
        ]
        if missing_aggregate_members:
            joined = ", ".join(
                f"`{bundle_id}`" for bundle_id in missing_aggregate_members
            )
            raise ValidationPolicyError(
                f"Aggregate official bundles must declare members: {joined}."
            )
        for bundle_id in aggregate_bundle_ids:
            non_atomic_members = [
                member
                for member in bundles[bundle_id].members
                if bundles[member].kind != "atomic"
            ]
            if non_atomic_members:
                joined = ", ".join(f"`{member}`" for member in non_atomic_members)
                raise ValidationPolicyError(
                    f"bundles.{bundle_id}.members must reference only atomic bundles: {joined}."
                )

        levels_mapping = _expect_mapping(mapping.get("levels"), path="levels")
        unknown_level_ids = sorted(set(levels_mapping) - VALIDATION_LEVEL_IDS)
        if unknown_level_ids:
            joined = ", ".join(f"`{level_id}`" for level_id in unknown_level_ids)
            raise ValidationPolicyError(
                f"Unknown validation level identifiers in levels: {joined}."
            )

        missing_level_ids = [
            level_id
            for level_id in VALIDATION_LEVEL_ORDER
            if level_id not in levels_mapping
        ]
        if missing_level_ids:
            joined = ", ".join(f"`{level_id}`" for level_id in missing_level_ids)
            raise ValidationPolicyError(
                f"Missing validation level definitions for: {joined}."
            )

        levels = {
            level_id: ValidationLevel.from_dict(
                level_id,
                levels_mapping[level_id],
                bundles=bundles,
            )
            for level_id in VALIDATION_LEVEL_ORDER
        }
        observed_level_orders = sorted(level.order for level in levels.values())
        expected_level_orders = list(range(1, len(VALIDATION_LEVEL_ORDER) + 1))
        if observed_level_orders != expected_level_orders:
            raise ValidationPolicyError(
                "Validation levels must use the canonical order values "
                f"{expected_level_orders}, got {observed_level_orders}."
            )

        changed_surface_rules = mapping.get("changed_surface_rules", [])
        if not isinstance(changed_surface_rules, list):
            raise ValidationPolicyError(
                "changed_surface_rules must be a list when present."
            )
        normalized_changed_surface_rules = tuple(
            ChangedSurfaceRule.from_dict(
                rule,
                bundles=bundles,
                levels=levels,
                index=index,
            )
            for index, rule in enumerate(changed_surface_rules)
        )
        if not normalized_changed_surface_rules:
            raise ValidationPolicyError(
                "changed_surface_rules must not be empty once level-selection semantics are defined."
            )
        duplicate_rule_ids = sorted(
            {
                rule.rule_id
                for rule in normalized_changed_surface_rules
                if [item.rule_id for item in normalized_changed_surface_rules].count(
                    rule.rule_id
                )
                > 1
            }
        )
        if duplicate_rule_ids:
            joined = ", ".join(f"`{rule_id}`" for rule_id in duplicate_rule_ids)
            raise ValidationPolicyError(
                f"changed_surface_rules contains duplicate ids: {joined}."
            )

        exceptions = mapping.get("exceptions", [])
        if not isinstance(exceptions, list):
            raise ValidationPolicyError("exceptions must be a list when present.")
        normalized_exceptions = tuple(
            ValidationPolicyException.from_dict(item, index=index)
            for index, item in enumerate(exceptions)
        )
        if not normalized_exceptions:
            raise ValidationPolicyError(
                "exceptions must not be empty once explicit policy-backed divergence is defined."
            )
        duplicate_exception_ids = sorted(
            {
                item.exception_id
                for item in normalized_exceptions
                if [entry.exception_id for entry in normalized_exceptions].count(
                    item.exception_id
                )
                > 1
            }
        )
        if duplicate_exception_ids:
            joined = ", ".join(
                f"`{exception_id}`" for exception_id in duplicate_exception_ids
            )
            raise ValidationPolicyError(f"exceptions contains duplicate ids: {joined}.")

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
