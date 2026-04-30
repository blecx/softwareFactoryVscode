# Validation policy contract and official bundle taxonomy

This document records the canonical validation-policy authority surface introduced for issue `#226` under umbrella issue `#225`.

- **Status:** canonical bundle-taxonomy contract
- **Authoritative config:** [`../../configs/validation_policy.yml`](../../configs/validation_policy.yml)
- **Schema/loader:** [`../../factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py)
- **Current boundary:** this slice defines the official bundle identifiers, required bundle metadata, and bounded watchdog contract. It does **not** yet define the four validation levels, changed-surface resolution rules, explicit local-vs-GitHub exceptions, or the full invalid-policy lock suite.

## Why this surface exists

Phase 1 documented the current derivative validation surfaces and the current accidental drift between local and GitHub execution. Phase 2 needs one repo-owned authority surface that later implementation can consume instead of continuing to invent bundle meaning independently in scripts, workflow YAML, or docs.

For this repository, that authority surface is:

1. [`configs/validation_policy.yml`](../../configs/validation_policy.yml) — the canonical machine-readable bundle taxonomy and bounded metadata surface.
2. [`factory_runtime/agents/validation_policy.py`](../../factory_runtime/agents/validation_policy.py) — the strict schema validator/loader for that surface.
3. This contract note — the maintainer-facing explanation of what the official bundle names mean and where later migration must consume them.

## Current boundary and deferred scope

Issue `#226` intentionally stops at taxonomy and schema ownership.

What this slice defines now:

- one authoritative config location for official validation bundle identifiers;
- required bundle metadata (`kind`, `owner`, `summary`, current derivative labels, and bounded watchdog metadata);
- canonical placeholder identifiers for aggregate bundles such as `baseline`, `merge-full`, and `production`; and
- empty reserved sections (`levels`, `changed_surface_rules`, and `exceptions`) so later slices can extend the same contract rather than reset it.

What this slice defers intentionally:

- issue `#227` — four level compositions, changed-surface mapping, escalation semantics, aggregate membership, and explicit local-vs-GitHub exceptions;
- issue `#228` — the broader valid/invalid policy contract lock, including missing watchdog metadata, over-budget bundles, invalid bundle references, malformed exceptions, and other forbidden states; and
- any migration of [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py) or [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml) to consume the new policy directly.

## Official bundle taxonomy

| Official bundle     | Kind      | Primary owner         | Meaning today                                                                                                                            | Current derivative labels                                       |
| ------------------- | --------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `baseline`          | aggregate | `validation-contract` | Reserved identifier for the smallest official mirror bundle once issue `#227` defines composition.                                       | none yet                                                        |
| `docs-contract`     | atomic    | `docs`                | Release/docs contract checks that protect canonical docs, manifests, and reader-facing authority surfaces.                               | `release-contract`, `docs-workflow`, `Production Docs Contract` |
| `workflow-contract` | atomic    | `workflow`            | Template, workflow-routing, and queue-guardrail checks that keep issue execution deterministic.                                          | `release-contract`, `pr-template`, `docs-workflow`              |
| `install-runtime`   | atomic    | `install-runtime`     | Install-surface and generated-workspace contract checks.                                                                                 | `install-surface`                                               |
| `runtime-manager`   | atomic    | `runtime-manager`     | Runtime manager and lifecycle truth checks.                                                                                              | `runtime-manager`                                               |
| `multi-tenant`      | atomic    | `shared-tenancy`      | Tenant-isolation and shared-tenancy contract checks.                                                                                     | `quota-tenancy`                                                 |
| `quota-policy`      | atomic    | `quota-governance`    | Quota-governance and bounded-budget contract checks.                                                                                     | `quota-tenancy`                                                 |
| `integration`       | atomic    | `integration`         | Architectural boundary and integration checks beyond unit-only coverage.                                                                 | `integration`, `Architectural Boundary Tests`                   |
| `docker-builds`     | atomic    | `docker`              | Docker image build parity checks.                                                                                                        | `docker-builds`, `Production Docker Build Parity`               |
| `runtime-proofs`    | atomic    | `docker`              | Promoted Docker/runtime proof checks for production-grade evidence.                                                                      | `runtime-proofs`, `Production Runtime Proofs`                   |
| `merge-full`        | aggregate | `validation-contract` | Reserved identifier for the full merge-grade official mirror bundle once issue `#227` defines composition.                               | none yet                                                        |
| `production`        | aggregate | `validation-contract` | Canonical production authority mirror aligned to the aggregate production gate while exact composition remains deferred to issue `#227`. | `Internal Production Gate — Docker Parity & Recovery Proofs`    |

## Bounded watchdog contract introduced here

Every official bundle definition must now carry bounded runtime metadata.

Current schema requirements:

- `watchdog.max_minutes` must be a positive integer and must stay at or below `45` minutes;
- `watchdog.timeout_kind` must currently be `event-driven-deadline`; and
- aggregate placeholders still need bounded watchdog metadata even before their member bundles are populated.

This keeps the taxonomy compatible with the repository rule that CI-critical validation should remain split into bounded bundles with explicit deadlines rather than indefinite waits.

## Downstream surfaces that must consume these names later

The following surfaces remain derivative today and must migrate intentionally in later phases instead of continuing to define shadow bundle truth:

- [`../../scripts/local_ci_parity.py`](../../scripts/local_ci_parity.py)
- [`../../.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
- [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md)
- [`../setup-github-repository.md`](../setup-github-repository.md)
- [`VALIDATION-PARITY-INVENTORY.md`](VALIDATION-PARITY-INVENTORY.md)
- [`../architecture/ADR-006-Local-CI-Parity-Prechecks.md`](../architecture/ADR-006-Local-CI-Parity-Prechecks.md)

Until those surfaces are updated on purpose, the policy file here is the canonical contract and the existing workflow/script labels remain derivative compatibility surfaces only.
