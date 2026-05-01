"""Shared validation plan resolver for local and GitHub execution.

Issue #234 introduces the first shared-engine consumer of the canonical
validation policy. Given a diff plus a requested validation level, the
resolver returns the canonical official bundle plan, the effective execution
lane, the applicable policy exceptions for the chosen context, and a
deterministic explanation of why that plan was selected.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable

from factory_runtime.agents.validation_policy import ValidationPolicy

ALLOWED_VALIDATION_RESOLUTION_CONTEXTS = frozenset({"local", "github"})


class ValidationPlanResolverError(ValueError):
    """Raised when shared validation plan resolution input is invalid."""


@dataclass(frozen=True, slots=True)
class ValidationPlanReason:
    """Deterministic explanation entry for one resolution decision."""

    reason_type: str
    summary: str
    bundle_ids: tuple[str, ...] = ()
    matched_paths: tuple[str, ...] = ()
    rule_id: str | None = None
    level_id: str | None = None
    exception_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationPlanExceptionBehavior:
    """Context-specific policy exception behavior attached to a plan."""

    exception_id: str
    summary: str
    applies_to_level: str
    context: str
    context_behavior: str
    rationale: str


@dataclass(frozen=True, slots=True)
class ValidationPlan:
    """Resolved official bundle plan for one diff, level, and context."""

    context: str
    changed_paths: tuple[str, ...]
    requested_level: str
    effective_level: str
    execution_level: str
    default_bundle: str
    resolved_bundle_ids: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]
    selected_atomic_bundles: tuple[str, ...]
    effective_atomic_bundles: tuple[str, ...]
    escalation_bundle: str | None
    applicable_exceptions: tuple[ValidationPlanExceptionBehavior, ...]
    reasons: tuple[ValidationPlanReason, ...]


def resolve_validation_plan(
    *,
    changed_paths: tuple[str, ...],
    requested_level: str,
    context: str,
    policy: ValidationPolicy | None = None,
) -> ValidationPlan:
    """Resolve the canonical validation bundle plan for one diff and context."""

    resolved_policy = (
        policy if policy is not None else ValidationPolicy.load_canonical()
    )

    if requested_level not in resolved_policy.levels:
        raise ValidationPlanResolverError(
            f"requested_level must be one of {tuple(resolved_policy.levels)}, got `{requested_level}`."
        )
    if context not in ALLOWED_VALIDATION_RESOLUTION_CONTEXTS:
        raise ValidationPlanResolverError(
            f"context must be one of {tuple(sorted(ALLOWED_VALIDATION_RESOLUTION_CONTEXTS))}, got `{context}`."
        )

    normalized_paths = _normalize_paths(changed_paths)
    requested_level_config = resolved_policy.levels[requested_level]

    if requested_level_config.strategy == "aggregate":
        execution_level = requested_level
        default_bundle = requested_level_config.default_bundle
        applicable_exceptions = _applicable_exceptions(
            resolved_policy,
            execution_level=execution_level,
            context=context,
        )
        reasons = [
            ValidationPlanReason(
                reason_type="default-bundle",
                summary=(
                    f"Level `{requested_level}` resolves directly to aggregate bundle "
                    f"`{default_bundle}`."
                ),
                level_id=requested_level,
                bundle_ids=(default_bundle,),
            )
        ]
        reasons.extend(_exception_reasons(applicable_exceptions))
        return ValidationPlan(
            context=context,
            changed_paths=normalized_paths,
            requested_level=requested_level,
            effective_level=requested_level,
            execution_level=execution_level,
            default_bundle=default_bundle,
            resolved_bundle_ids=(default_bundle,),
            matched_rule_ids=(),
            selected_atomic_bundles=(),
            effective_atomic_bundles=resolved_policy.bundles[default_bundle].members,
            escalation_bundle=None,
            applicable_exceptions=applicable_exceptions,
            reasons=tuple(reasons),
        )

    matched_rule_paths = _selected_rule_matches(resolved_policy, normalized_paths)
    matched_rules = tuple(rule for rule, _ in matched_rule_paths)

    effective_level = max(
        (requested_level, *(rule.minimum_level for rule in matched_rules)),
        key=lambda level_id: resolved_policy.levels[level_id].order,
    )
    effective_level_config = resolved_policy.levels[effective_level]
    default_bundle = effective_level_config.default_bundle
    selected_atomic_bundles = _unique_strings(
        bundle_id for rule in matched_rules for bundle_id in rule.bundles
    )
    escalation_bundle = _highest_escalation_bundle(resolved_policy, matched_rules)
    execution_level = _execution_level_for_plan(
        resolved_policy,
        effective_level=effective_level,
        escalation_bundle=escalation_bundle,
    )
    resolved_bundle_ids, effective_atomic_bundles = _resolved_bundle_plan(
        resolved_policy,
        default_bundle=default_bundle,
        selected_atomic_bundles=selected_atomic_bundles,
        escalation_bundle=escalation_bundle,
    )
    applicable_exceptions = _applicable_exceptions(
        resolved_policy,
        execution_level=execution_level,
        context=context,
    )

    reasons: list[ValidationPlanReason] = [
        ValidationPlanReason(
            reason_type="requested-level",
            summary=f"Requested level `{requested_level}` entered the shared resolver.",
            level_id=requested_level,
        ),
        ValidationPlanReason(
            reason_type="default-bundle",
            summary=(
                f"Level `{effective_level}` starts from aggregate bundle `{default_bundle}`."
            ),
            level_id=effective_level,
            bundle_ids=(default_bundle,),
        ),
    ]
    reasons.extend(
        ValidationPlanReason(
            reason_type="matched-rule",
            summary=(
                f"Rule `{rule.rule_id}` matched the changed paths and selected "
                f"official bundles {rule.bundles}."
            ),
            rule_id=rule.rule_id,
            level_id=rule.minimum_level,
            bundle_ids=rule.bundles,
            matched_paths=matched_paths,
        )
        for rule, matched_paths in matched_rule_paths
    )

    if effective_level != requested_level:
        reasons.append(
            ValidationPlanReason(
                reason_type="minimum-level-promotion",
                summary=(
                    f"Matched rules promoted requested level `{requested_level}` to "
                    f"`{effective_level}`."
                ),
                level_id=effective_level,
                bundle_ids=(default_bundle,),
            )
        )

    if escalation_bundle is not None:
        reasons.append(
            ValidationPlanReason(
                reason_type="escalation",
                summary=(
                    f"Matched rules escalated execution to aggregate bundle "
                    f"`{escalation_bundle}` at level `{execution_level}`."
                ),
                level_id=execution_level,
                bundle_ids=(escalation_bundle,),
            )
        )

    reasons.extend(_exception_reasons(applicable_exceptions))

    return ValidationPlan(
        context=context,
        changed_paths=normalized_paths,
        requested_level=requested_level,
        effective_level=effective_level,
        execution_level=execution_level,
        default_bundle=default_bundle,
        resolved_bundle_ids=resolved_bundle_ids,
        matched_rule_ids=tuple(rule.rule_id for rule in matched_rules),
        selected_atomic_bundles=selected_atomic_bundles,
        effective_atomic_bundles=effective_atomic_bundles,
        escalation_bundle=escalation_bundle,
        applicable_exceptions=applicable_exceptions,
        reasons=tuple(reasons),
    )


def _normalize_paths(changed_paths: tuple[str, ...]) -> tuple[str, ...]:
    return _unique_strings(str(PurePosixPath(path)) for path in changed_paths)


def _matched_paths_for_rule(
    changed_paths: tuple[str, ...], include_paths: tuple[str, ...]
) -> tuple[str, ...]:
    return tuple(
        path
        for path in changed_paths
        if any(_matches_include_path(path, pattern) for pattern in include_paths)
    )


def _matches_include_path(path: str, pattern: str) -> bool:
    normalized = str(PurePosixPath(path))
    normalized_pattern = str(PurePosixPath(pattern))
    pure_path = PurePosixPath(normalized)

    if normalized == normalized_pattern:
        return True

    if normalized_pattern.endswith("/**"):
        prefix = normalized_pattern[:-3].rstrip("/")
        return normalized == prefix or normalized.startswith(f"{prefix}/")

    return pure_path.match(normalized_pattern)


def _selected_rule_matches(
    policy: ValidationPolicy,
    changed_paths: tuple[str, ...],
) -> tuple[tuple[object, tuple[str, ...]], ...]:
    selected_paths_by_rule: dict[str, list[str]] = {}

    for path in changed_paths:
        path_matches: list[tuple[object, tuple[int, int, int]]] = []
        for rule in policy.changed_surface_rules:
            matching_scores = [
                _pattern_specificity(pattern)
                for pattern in rule.include_paths
                if _matches_include_path(path, pattern)
            ]
            if matching_scores:
                path_matches.append((rule, max(matching_scores)))

        if not path_matches:
            continue

        highest_score = max(score for _, score in path_matches)
        for rule, score in path_matches:
            if score != highest_score:
                continue
            selected_paths_by_rule.setdefault(rule.rule_id, []).append(path)

    return tuple(
        (rule, tuple(selected_paths_by_rule[rule.rule_id]))
        for rule in policy.changed_surface_rules
        if rule.rule_id in selected_paths_by_rule
    )


def _pattern_specificity(pattern: str) -> tuple[int, int, int]:
    normalized_pattern = str(PurePosixPath(pattern))
    parts = PurePosixPath(normalized_pattern).parts
    wildcard_parts = sum(1 for part in parts if any(char in part for char in "*?[]"))
    concrete_parts = len(parts) - wildcard_parts
    is_exact = int(wildcard_parts == 0)
    return (is_exact, concrete_parts, len(normalized_pattern))


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _highest_escalation_bundle(
    policy: ValidationPolicy,
    matched_rules: tuple[object, ...],
) -> str | None:
    escalation_candidates = _unique_strings(
        rule.escalate_to for rule in matched_rules if rule.escalate_to is not None
    )
    if not escalation_candidates:
        return None
    return max(
        escalation_candidates,
        key=lambda bundle_id: _aggregate_bundle_level_order(policy, bundle_id),
    )


def _aggregate_bundle_level_order(policy: ValidationPolicy, bundle_id: str) -> int:
    for level in policy.levels.values():
        if level.default_bundle == bundle_id:
            return level.order
    return 0


def _execution_level_for_plan(
    policy: ValidationPolicy,
    *,
    effective_level: str,
    escalation_bundle: str | None,
) -> str:
    if escalation_bundle is None:
        return effective_level
    for level_id, level in policy.levels.items():
        if level.default_bundle == escalation_bundle:
            return level_id
    return effective_level


def _resolved_bundle_plan(
    policy: ValidationPolicy,
    *,
    default_bundle: str,
    selected_atomic_bundles: tuple[str, ...],
    escalation_bundle: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if escalation_bundle is not None:
        return (escalation_bundle,), policy.bundles[escalation_bundle].members

    default_members = policy.bundles[default_bundle].members
    additional_atomic_bundles = tuple(
        bundle_id
        for bundle_id in selected_atomic_bundles
        if bundle_id not in default_members
    )
    return (
        (default_bundle, *additional_atomic_bundles),
        _unique_strings((*default_members, *additional_atomic_bundles)),
    )


def _applicable_exceptions(
    policy: ValidationPolicy,
    *,
    execution_level: str,
    context: str,
) -> tuple[ValidationPlanExceptionBehavior, ...]:
    return tuple(
        ValidationPlanExceptionBehavior(
            exception_id=item.exception_id,
            summary=item.summary,
            applies_to_level=execution_level,
            context=context,
            context_behavior=(
                item.local_behavior if context == "local" else item.github_behavior
            ),
            rationale=item.rationale,
        )
        for item in policy.exceptions
        if execution_level in item.applies_to_levels
    )


def _exception_reasons(
    applicable_exceptions: tuple[ValidationPlanExceptionBehavior, ...],
) -> tuple[ValidationPlanReason, ...]:
    return tuple(
        ValidationPlanReason(
            reason_type="policy-exception",
            summary=(
                f"Policy exception `{item.exception_id}` applies to "
                f"`{item.applies_to_level}` for `{item.context}` resolution."
            ),
            level_id=item.applies_to_level,
            exception_id=item.exception_id,
        )
        for item in applicable_exceptions
    )
