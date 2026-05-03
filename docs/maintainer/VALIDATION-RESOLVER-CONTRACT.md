# Validation plan resolver contract

This document records the shared validation plan resolver introduced in issue `#234`
under umbrella issue `#233`. The resolver is the first shared-engine consumer
of the canonical validation policy and provides one deterministic,
caller-neutral entrypoint for validation bundle selection.

- **Status:** shared-engine validation plan resolution contract
- **Authoritative resolver implementation:** [`../../factory_runtime/agents/validation_plan_resolver.py`](../../factory_runtime/agents/validation_plan_resolver.py)
- **Canonical policy input:** [`../../configs/validation_policy.yml`](../../configs/validation_policy.yml)
- **Schema/loader for policy metadata:** [`../../factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py)
- **Downstream runner:** [`VALIDATION-RUNNER-CONTRACT.md`](VALIDATION-RUNNER-CONTRACT.md)

## Why this surface exists

Phase 2 established the canonical validation policy and bundle taxonomy.
Without a shared plan resolver, downstream callers like local wrappers and CI
workflows would have to reconstruct changed-surface matching, default bundle
expansion, and policy exception logic on their own. The shared resolver closes
this drift gap by centralizing how policy rules apply to arbitrary diffs and contexts.

## Resolver entrypoint and inputs

The entrypoint is `resolve_validation_plan` in [`../../factory_runtime/agents/validation_plan_resolver.py`](../../factory_runtime/agents/validation_plan_resolver.py).

It expects:
- `changed_paths` (`tuple[str, ...]`): the surface changes observed in the diff.
- `requested_level` (`str`): the base intent requested by the caller (one of the four defined policy levels).
- `context` (`str`): the execution context (must be `local` or `github`).
- `policy` (optional `ValidationPolicy`): the policy to resolve against; defaults to canonical config.

## Resolver output and explanation

The resolver returns a `ValidationPlan` representing the definitive blueprint for execution.
It explicitly avoids running the execution itself.

The `ValidationPlan` includes:
- **Plan execution metadata**: `context`, `changed_paths`, and the `requested_level`.
- **Level promotion**: the `effective_level` and the final `execution_level`.
- **Bundle breakdown**: the `resolved_bundle_ids` containing the directly chosen bundles, and `effective_atomic_bundles` mapping to the flattened list of explicit atomic checks.
- **Rule matching**: `matched_rule_ids`, showing which `changed_surface_rules` mapped the paths to atomic bundles.
- **Escalations**: `escalation_bundle` tracking any mandatory promotion mandated by matched rules.
- **Exceptions**: `applicable_exceptions` extracting `ValidationPlanExceptionBehavior` constraints for the caller's context.
- **Decision explanation**: `reasons`, a deterministic trace recording the fallback/matched logic that selected the plan, aiding maintainer discoverability.

## Lock test surfaces

- [`../../tests/test_validation_plan_resolver.py`](../../tests/test_validation_plan_resolver.py) — Canonical resolution validation, test path coverage, matched rule verification, and exception behavior logic.
- [`../../tests/test_validation_resolver_docs_contract.py`](../../tests/test_validation_resolver_docs_contract.py) — Maintainer-facing discoverability and authority-routing lock for this resolver contract note.
