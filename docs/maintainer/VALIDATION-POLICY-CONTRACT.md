# Validation policy contract and official bundle taxonomy

This document records the canonical validation-policy authority surface introduced for issue `#226`, extended for issue `#227`, and locked by the broader valid/invalid policy contract lock suite in issue `#228` under umbrella issue `#225`.

- **Status:** canonical bundle-taxonomy and level-selection contract
- **Authoritative config:** [`../../configs/validation_policy.yml`](../../configs/validation_policy.yml)
- **Schema/loader:** [`../../factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py)
- **Current boundary:** this slice defines the official bundle identifiers, required bundle metadata, bounded watchdog contract, four validation levels, representative changed-surface resolution rules, aggregate escalation semantics, explicit local-vs-GitHub exceptions, and the contract tests that lock those semantics against invalid-policy drift. It still does **not** yet migrate workflow runners to consume these semantics directly.

## Why this surface exists

Phase 1 documented the current derivative validation surfaces and the current accidental drift between local and GitHub execution. Phase 2 needs one repo-owned authority surface that later implementation can consume instead of continuing to invent bundle meaning independently in scripts, workflow YAML, or docs.

For this repository, that authority surface is:

1. [`configs/validation_policy.yml`](../../configs/validation_policy.yml) — the canonical machine-readable bundle taxonomy and bounded metadata surface.
2. [`factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py) — the strict schema validator/loader for that surface.
3. This contract note — the maintainer-facing explanation of what the official bundle names mean and where later migration must consume them.

## Current boundary and deferred scope

Issues `#226`, `#227`, and `#228` establish the canonical contract surface and the broader valid/invalid policy contract lock around it.

What this slice defines now:

- one authoritative config location for official validation bundle identifiers;
- required bundle metadata (`kind`, `owner`, `summary`, current derivative labels, and bounded watchdog metadata);
- aggregate membership for the canonical `baseline`, `merge-full`, and `production` bundles;
- four validation levels that point back to those official bundles instead of inventing new level-specific bundle names;
- representative changed-surface mapping and escalation rules;
- explicit local-vs-GitHub exceptions with rationale; and
- contract tests that lock representative valid bundle-selection scenarios plus deterministic invalid-policy rejection cases.

What this slice defers intentionally:

- any migration of [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) or [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) to consume the new policy directly.

## Four-level validation model

| Level | Intent | Resolution rule |
| --- | --- | --- |
| `focused-local` (Level 1) | Smallest bounded local mirror for a specific changed surface. | Start from aggregate bundle `baseline`, add the atomic bundles selected by `changed_surface_rules`, and escalate only when the matching rule explicitly names `merge-full` or `production`. |
| `pr-update` (Level 2) | PR update mirror for the current diff. | Uses the same changed-surface-first selection model as `focused-local`, but it is the minimum level for broader PR-grade surfaces such as integration and validation-contract drift. |
| `merge` (Level 3) | Full merge mirror. | Resolves directly to aggregate bundle `merge-full`. |
| `production` (Level 4) | Production authority mirror. | Resolves directly to aggregate bundle `production`. |

The two changed-surface-driven levels intentionally point back to the same
official bundle taxonomy instead of inventing separate “Level 1” or “Level 2”
bundle names. That keeps later resolver/runner code aligned with one canonical
bundle vocabulary.

## Official bundle taxonomy

- `baseline` *(aggregate, owner `validation-contract`)* — smallest official mirror bundle composed of `docs-contract` + `workflow-contract` for changed-surface-driven local and PR-update validation. Current derivative labels: none yet.
- `docs-contract` *(atomic, owner `docs`)* — release/docs contract checks that protect canonical docs, manifests, and reader-facing authority surfaces. Current derivative labels: `release-contract`, `docs-workflow`, `Production Docs Contract`.
- `workflow-contract` *(atomic, owner `workflow`)* — template, workflow-routing, and queue-guardrail checks that keep issue execution deterministic. Current derivative labels: `release-contract`, `pr-template`, `docs-workflow`.
- `install-runtime` *(atomic, owner `install-runtime`)* — install-surface and generated-workspace contract checks. Current derivative labels: `install-surface`.
- `runtime-manager` *(atomic, owner `runtime-manager`)* — runtime manager and lifecycle truth checks. Current derivative labels: `runtime-manager`.
- `multi-tenant` *(atomic, owner `shared-tenancy`)* — tenant-isolation and shared-tenancy contract checks. Current derivative labels: `quota-tenancy`.
- `quota-policy` *(atomic, owner `quota-governance`)* — quota-governance and bounded-budget contract checks. Current derivative labels: `quota-tenancy`.
- `integration` *(atomic, owner `integration`)* — architectural boundary and integration checks beyond unit-only coverage. Current derivative labels: `integration`, `Architectural Boundary Tests`.
- `docker-builds` *(atomic, owner `docker`)* — Docker image build parity checks. Current derivative labels: `docker-builds`, `Production Docker Build Parity`.
- `runtime-proofs` *(atomic, owner `docker`)* — promoted Docker/runtime proof checks for production-grade evidence. Current derivative labels: `runtime-proofs`, `Production Runtime Proofs`.
- `merge-full` *(aggregate, owner `validation-contract`)* — full merge-grade official mirror aggregating every bounded atomic bundle: docs, workflow, install/runtime, tenancy/quota, integration, Docker builds, and runtime proofs. Current derivative labels: none yet.
- `production` *(aggregate, owner `validation-contract`)* — canonical production authority mirror aligned to the aggregate production gate and composed of `docs-contract`, `docker-builds`, and `runtime-proofs`. Current derivative labels: `Internal Production Gate — Docker Parity & Recovery Proofs`.

## Representative changed-surface selection rules

The canonical policy now records representative changed-surface classes so later
resolver/runner work can consume the same intent instead of reconstructing it
from ad-hoc workflow code.

| Rule id | Representative surfaces | Selected bundles | Minimum level | Explicit escalation |
| --- | --- | --- | --- | --- |
| `docs-authority-surface` | `README.md`, release docs, `docs/**`, canonical manifests | `docs-contract` | `focused-local` | none |
| `workflow-contract-surface` | `.github/**`, `.copilot/**`, queue/prompt routing docs, PR-template validation helpers | `workflow-contract` | `focused-local` | none |
| `install-runtime-surface` | install/update scripts and generated-workspace contract tests | `install-runtime` | `focused-local` | none |
| `runtime-manager-surface` | manager-backed runtime package, runtime manager tests, runtime mode tests | `runtime-manager` | `focused-local` | none |
| `quota-tenancy-surface` | shared-tenancy, quota governance, tenant-isolation tests | `multi-tenant`, `quota-policy` | `focused-local` | none |
| `integration-boundary-surface` | `compose/**`, `tests/run-integration-test.sh` | `integration` | `pr-update` | none |
| `validation-contract-surface` | canonical validation policy/config, local parity wrapper, CI workflow, parity inventory | `docs-contract`, `workflow-contract` | `pr-update` | `merge-full` |
| `production-authority-surface` | `docker/**`, production-readiness docs/runbooks, Docker runtime-proof tests | `docker-builds`, `runtime-proofs` | `pr-update` | `production` |

Two escalation cases matter on purpose:

- `validation-contract-surface` escalates to `merge-full` because changing the
  validation contract itself must re-prove the whole merge-grade official
  bundle set, not a narrow targeted replay.
- `production-authority-surface` escalates to `production` because those
  surfaces map to the same aggregate authority lane GitHub already treats as the
  final production gate.

## Explicit local-vs-GitHub exceptions

The policy now records the allowed differences explicitly instead of hiding them
inside wrapper code or workflow YAML.

| Exception id | Local behavior | GitHub behavior | Why the divergence is allowed |
| --- | --- | --- | --- |
| `github-event-metadata` | Local callers provide explicit diff/base context and may use repo-owned one-shot GitHub queries. | GitHub derives refs and selectors from `pull_request` / `push` event payloads. | Event metadata changes how the diff is discovered, not what the selected bundles mean. |
| `fresh-checkout-bootstrap` | Local parity may reuse the active worktree or opt into `--fresh-checkout`. | GitHub always starts from a fresh checkout and reruns bootstrap. | Bootstrap substrate differs, but bundle selection must stay the same. |
| `github-permissions-and-protected-resources` | Local parity uses repo-local files and read-only/pager-free queries. | GitHub CI/PR flows run with repository-scoped tokens and protected-resource permissions. | Permission semantics are explicit environment differences, not hidden bundle drift. |
| `runner-ownership-parity` | Local production mirrors may rely on the bind-mount ownership probe or fresh-checkout guidance. | GitHub production lanes run on GitHub-hosted runner ownership semantics. | Runner ownership quirks are an explicit production-only exception. |

## Bounded watchdog contract introduced here

Every official bundle definition must now carry bounded runtime metadata.

Current schema requirements:

- `watchdog.max_minutes` must be a positive integer and must stay at or below `45` minutes;
- `watchdog.timeout_kind` must currently be `event-driven-deadline`; and
- aggregate bundles still need bounded watchdog metadata even after their member bundles are populated.

This keeps the taxonomy compatible with the repository rule that CI-critical validation should remain split into bounded bundles with explicit deadlines rather than indefinite waits.

## Contract lock test surfaces

Issue `#228` lands the broader repository-owned lock suite that future resolver,
runner, and workflow work must keep green.

- [`../../tests/test_validation_policy.py`](../../tests/test_validation_policy.py) — canonical happy-path load and authority smoke test.
- [`../../tests/test_validation_policy_selection_contract.py`](../../tests/test_validation_policy_selection_contract.py) — representative valid bundle-selection scenarios, escalation boundaries, and explicit exception coverage.
- [`../../tests/test_validation_policy_errors.py`](../../tests/test_validation_policy_errors.py) — deterministic invalid-policy rejection cases including missing watchdog metadata, budget ceiling violations, bad bundle references, malformed exceptions, and duplicate/forbidden selection state.
- [`../../tests/test_validation_policy_docs_contract.py`](../../tests/test_validation_policy_docs_contract.py) — contributor-facing discoverability and authority-routing lock for this contract note.

## Downstream surfaces that must consume these semantics later

The following surfaces remain derivative today and must migrate intentionally in later phases instead of continuing to define shadow validation semantics:

- [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)
- [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md)
- [`../setup-github-repository.md`](../setup-github-repository.md)
- [`../CHEAT_SHEET.md`](../CHEAT_SHEET.md)
- [`../HANDOUT.md`](../HANDOUT.md)
- [`VALIDATION-PARITY-INVENTORY.md`](VALIDATION-PARITY-INVENTORY.md)
- [`../architecture/ADR-006-Local-CI-Parity-Prechecks.md`](../architecture/ADR-006-Local-CI-Parity-Prechecks.md)

Until those surfaces are updated on purpose, the policy file here is the canonical contract and the existing workflow/script labels remain derivative compatibility surfaces only.
