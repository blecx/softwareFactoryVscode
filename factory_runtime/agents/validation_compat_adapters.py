"""Transitional compatibility adapters for shared validation engine callers.

Issue #236 adds a thin adapter layer for existing wrapper/task entrypoints that
still need to preserve caller continuity while delegating execution to the
shared validation resolver/runner contract.

These adapters are intentionally temporary:

- they may translate legacy entrypoint inputs into official atomic bundle ids;
- they must not invent a second validation policy or timeout contract; and
- they should disappear once callers use the shared engine contract directly.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Sequence

from factory_runtime.agents.validation_plan_resolver import (
    ValidationPlan,
    ValidationPlanReason,
    resolve_validation_plan,
)
from factory_runtime.agents.validation_policy import ValidationPolicy
from factory_runtime.agents.validation_runner import ValidationRunnerRequest

COMPATIBILITY_ADAPTER_DEPRECATION_NOTE = (
    "Compatibility adapters are transitional callers of the shared validation "
    "engine. They must not become a second authority surface."
)
LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE = (
    "scripts/local_ci_parity.py --mode production --production-groups-only"
)


class ValidationCompatibilityAdapterError(ValueError):
    """Raised when a compatibility adapter request is not valid."""


def build_explicit_compatibility_plan(
    *,
    bundle_ids: Sequence[str],
    requested_level: str,
    context: str,
    compatibility_surface: str,
    policy: ValidationPolicy | None = None,
) -> ValidationPlan:
    """Build a temporary explicit-bundle plan on top of the shared resolver.

    Compatibility callers sometimes need to keep a legacy entrypoint alive while
    delegating execution to the shared engine. This helper keeps the requested
    level, context, policy exceptions, and bundle metadata anchored to the
    canonical policy while swapping the effective bundle list to an explicit set
    of official atomic bundles.
    """

    resolved_policy = (
        policy if policy is not None else ValidationPolicy.load_canonical()
    )
    normalized_bundle_ids = tuple(
        dict.fromkeys(
            bundle_id
            for bundle_id in (str(item).strip() for item in bundle_ids)
            if bundle_id
        )
    )
    if not normalized_bundle_ids:
        raise ValidationCompatibilityAdapterError(
            "bundle_ids must contain at least one official atomic bundle."
        )

    unknown_bundle_ids = tuple(
        bundle_id
        for bundle_id in normalized_bundle_ids
        if bundle_id not in resolved_policy.bundles
    )
    if unknown_bundle_ids:
        raise ValidationCompatibilityAdapterError(
            "Compatibility adapters can only target known official bundles; got "
            f"{unknown_bundle_ids}."
        )

    non_atomic_bundle_ids = tuple(
        bundle_id
        for bundle_id in normalized_bundle_ids
        if resolved_policy.bundles[bundle_id].kind != "atomic"
    )
    if non_atomic_bundle_ids:
        raise ValidationCompatibilityAdapterError(
            "Compatibility adapters can only target official atomic bundles; got "
            f"{non_atomic_bundle_ids}."
        )

    base_plan = resolve_validation_plan(
        changed_paths=(),
        requested_level=requested_level,
        context=context,
        policy=resolved_policy,
    )
    compatibility_reason = ValidationPlanReason(
        reason_type="compatibility-adapter",
        summary=(
            f"Compatibility surface `{compatibility_surface}` delegated to the "
            f"shared validation engine for official atomic bundles {normalized_bundle_ids}. "
            f"{COMPATIBILITY_ADAPTER_DEPRECATION_NOTE}"
        ),
        bundle_ids=normalized_bundle_ids,
        level_id=base_plan.execution_level,
    )
    return replace(
        base_plan,
        resolved_bundle_ids=normalized_bundle_ids,
        matched_rule_ids=(),
        selected_atomic_bundles=normalized_bundle_ids,
        effective_atomic_bundles=normalized_bundle_ids,
        escalation_bundle=None,
        reasons=(*base_plan.reasons, compatibility_reason),
    )


def build_local_ci_production_groups_runner_request(
    *,
    repo_root: Path,
    base_rev: str,
    head_rev: str,
    python_executable: str,
    selected_groups: Sequence[str],
    policy: ValidationPolicy | None = None,
) -> ValidationRunnerRequest:
    """Build a shared-runner request for local-ci production diagnostic groups."""

    resolved_policy = (
        policy if policy is not None else ValidationPolicy.load_canonical()
    )
    plan = build_explicit_compatibility_plan(
        bundle_ids=tuple(selected_groups),
        requested_level="production",
        context="local",
        compatibility_surface=LOCAL_CI_PRODUCTION_GROUPS_ONLY_COMPATIBILITY_SURFACE,
        policy=resolved_policy,
    )
    return ValidationRunnerRequest(
        repo_root=repo_root,
        plan=plan,
        base_rev=base_rev,
        head_rev=head_rev,
        python_executable=python_executable,
    )
