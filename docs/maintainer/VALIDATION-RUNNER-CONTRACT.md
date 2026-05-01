# Validation runner contract and structured reporting

This document records the shared validation runner introduced for issue `#235`
under umbrella issue `#233`, after issue `#234` landed the shared validation
plan resolver and issue `#236` added the first thin compatibility adapters for
legacy caller continuity. The runner is the first repo-owned execution surface
that consumes the canonical validation policy and resolver output together
without inventing a second caller-specific bundle taxonomy.

- **Status:** shared-engine runner/reporting contract
- **Authoritative resolver input:** [`../../factory_runtime/agents/validation_plan_resolver.py`](../../factory_runtime/agents/validation_plan_resolver.py)
- **Authoritative runner/report implementation:** [`../../factory_runtime/agents/validation_runner.py`](../../factory_runtime/agents/validation_runner.py)
- **Canonical policy input:** [`../../configs/validation_policy.yml`](../../configs/validation_policy.yml)
- **Schema/loader for policy metadata:** [`../../factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py)
- **Compatibility adapter boundary:** [`../../factory_runtime/agents/validation_compat_adapters.py`](../../factory_runtime/agents/validation_compat_adapters.py)
- **Current boundary:** this slice executes the resolved official atomic bundle plan, honors per-bundle watchdog metadata from the canonical policy, and emits one structured report contract with per-bundle status, timing, and terminal outcome details. Issue `#236` also lets the `--mode production --production-groups-only` path in [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) delegate to the shared runner through an explicit compatibility adapter. The default local aggregate flow and [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) still do **not** yet call the shared runner by default.

## Why this surface exists

Phase 2 established the canonical validation policy and bundle taxonomy. Issue
`#234` then resolved the official bundle plan deterministically for local and
GitHub contexts. Issue `#235` closes the next drift gap: execution and
reporting.

Without one shared runner, local wrappers, workflow jobs, and watchdog-aware
diagnostics would keep reconstructing:

- which official bundles actually ran,
- which per-bundle watchdog budget applied,
- what the terminal blocking outcome was, and
- how callers should report the same failure to humans and CI logs.

The shared runner becomes the common engine/reporting substrate so later local
and GitHub caller migrations can consume one repo-owned contract instead of
continuing to bolt on separate reporting formats.

## Current execution boundary

The shared runner currently guarantees the following:

1. It accepts a resolved [`ValidationPlan`](../../factory_runtime/agents/validation_plan_resolver.py) instead of performing changed-surface selection itself.
2. It executes only the official **atomic** bundles listed in `plan.effective_atomic_bundles`; aggregate bundles are resolved before execution.
3. It applies the canonical bundle watchdog contract from [`../../configs/validation_policy.yml`](../../configs/validation_policy.yml), using each bundle's `watchdog.max_minutes` / `watchdog.timeout_kind` metadata as the shared engine budget instead of caller-specific defaults.
4. It records a structured per-bundle report with step-level command/check detail, elapsed time, and blocking outcome.
5. It fast-fails on the first blocking bundle outcome by default and records later bundles as skipped rather than pretending they ran.

## Structured report contract

The runner emits one structured report object (`ValidationRunReport`) with:

- plan metadata: context, requested/effective/execution level, matched rules,
  resolved bundle ids, effective atomic bundles, escalation bundle, and policy
  exceptions;
- run timing: start timestamp, end timestamp, total elapsed seconds, and the
  terminal outcome for the full run;
- per-bundle reporting: official bundle id, owner, kind, derivative labels,
  watchdog budget, timeout kind, per-bundle status, timing, and optional skip
  reason;
- per-step reporting inside each bundle: step id, summary, command,
  environment overrides, timing, exit code, stdout/stderr, failure summary, and
  whether the step result came from shared-step caching.

This report shape is intentionally caller-neutral. Local CLI output, CI job
logs, and future watchdog-specific diagnostics should all derive from the same
structured source instead of inventing separate ad-hoc formats.

## Policy and watchdog inputs consumed here

The runner is required to honor the canonical policy inputs rather than caller
defaults.

- Bundle order and aggregate expansion come from the resolved
  `ValidationPlan.effective_atomic_bundles`.
- Bundle ownership, summary, derivative labels, and bounded runtime metadata
  come from [`../../factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py).
- The effective bundle budget is the policy-backed `watchdog.max_minutes`
  (subject to the documented hard ceiling surfaced there through
  `effective_budget_minutes`).
- The runner currently assumes the canonical timeout kind remains
  `event-driven-deadline`, matching the policy contract.

## Caller boundary and deferred migrations

Issue `#235` intentionally stopped at the shared engine/report contract. Issue
`#236` starts the compatibility migration without making those adapters a new
authority surface.

Still deferred after issue `#236`:

- making [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)
  use the shared runner as its default execution path for the standard path,
  the aggregate production gate, and legacy pytest-bundle replays;
- migrating [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
  jobs to consume the same report contract directly; and
- removing the temporary compatibility adapters once those callers consume the
  shared runner/report contract directly.

The compatibility adapters are intentionally narrow:

- they may translate legacy caller inputs into official atomic bundle ids;
- they must keep bundle selection, watchdog semantics, and metadata anchored to
  the canonical policy and resolver; and
- they must be documented as transitional callers, not new normative surfaces.

Those later migrations must reference this runner contract, the shared resolver,
the canonical validation policy, and [`../architecture/ADR-006-Local-CI-Parity-Prechecks.md`](../architecture/ADR-006-Local-CI-Parity-Prechecks.md) instead of inventing a fresh local-vs-GitHub execution contract.

## Lock test surfaces

- [`../../tests/test_validation_runner.py`](../../tests/test_validation_runner.py) — shared runner execution/reporting contract coverage, timeout behavior, fast-fail skip semantics, and official bundle registration.
- [`../../tests/test_validation_compat_adapters.py`](../../tests/test_validation_compat_adapters.py) — compatibility-adapter request/plan coverage plus local-ci shared-runner delegation regression locks.
- [`../../tests/test_validation_runner_docs_contract.py`](../../tests/test_validation_runner_docs_contract.py) — maintainer-facing discoverability and authority-routing lock for this runner contract note.
- [`../../tests/test_validation_plan_resolver.py`](../../tests/test_validation_plan_resolver.py) — shared plan resolution behavior that feeds the runner.
- [`../../tests/test_validation_policy_selection_contract.py`](../../tests/test_validation_policy_selection_contract.py) — policy-backed selection scenarios that determine which official bundles the runner must execute.
