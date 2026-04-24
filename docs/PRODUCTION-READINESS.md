# Internal Production Readiness Contract

This document is the canonical operator-facing contract for when `softwareFactoryVscode` may be described as production ready.

`docs/PRODUCTION-READINESS-PLAN.md` is the implementation roadmap for reaching this contract. It is not the readiness authority by itself.

## Status

`softwareFactoryVscode` is **not** entitled to claim full internal production readiness merely because the current default branch ships a strong namespace-first baseline.

The repository may be described as production ready only after every blocking requirement in this contract is satisfied and the final sign-off evidence has been recorded.

## Supported production boundary

The supported production target is **internal, self-hosted production** for the current namespace-first harness and manager-backed runtime model.

That boundary assumes:

- the canonical installed runtime contract remains under `.copilot/softwareFactoryVscode/` per `ADR-012`;
- the supported operator entrypoint is the generated `software-factory.code-workspace` file;
- runtime truth comes from the manager-backed snapshot and readiness surfaces exposed through `scripts/factory_stack.py` and `scripts/verify_factory_install.py`;
- shared-capable services follow the deliberate, evidence-backed promotion rules from `ADR-008`; and
- production readiness claims stay aligned with the MCP runtime authority defined by `ADR-014`.

## Explicitly out of scope

The repository must **not** claim this contract covers:

- external hosted multi-tenant SaaS production;
- customer-facing internet-hosted tenancy, billing, or SaaS authentication boundaries;
- blanket claims that every MCP service is globally shared or that shared mode is the default operator path; or
- any second lifecycle, readiness, or runtime-truth authority outside the manager-backed contract.

## Normative readiness authorities

The following sources define the readiness boundary and must stay aligned:

- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/architecture/ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`
- `docs/architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`
- `scripts/factory_stack.py` for canonical lifecycle, `preflight`, and `status`
- `scripts/verify_factory_install.py` for installation/runtime verification
- `scripts/local_ci_parity.py` for the repo's default CI-parity baseline
- `docs/PRODUCTION-READINESS-PLAN.md` for the bounded implementation roadmap

Operator-facing summaries in `README.md`, `docs/INSTALL.md`, `docs/CHEAT_SHEET.md`, and `docs/HANDOUT.md` must defer to this document rather than define a competing readiness story.

## Blocking requirements for an internal production claim

A final internal-production claim requires all of the following to be true:

1. An explicit internal-production runtime mode exists and fails closed on missing live configuration.
2. Production-required secrets and live config are validated, placeholders are rejected, and production mode does not silently downgrade to mock behavior.
3. Docker build parity is part of a blocking production gate.
4. At least one repeatable Docker E2E runtime proof is part of a blocking production gate.
5. Stateful runtime data can be backed up through a supported command with documented preconditions, metadata, and checksums.
6. Stateful runtime data can be restored through a supported workflow with a documented recovery roundtrip proof.
7. Operators have machine-readable runtime diagnostics derived from the manager-backed snapshot/readiness contract.
8. Incident-response and day-two operator runbooks exist for the supported internal runtime model.
9. One canonical internal production-readiness gate aggregates the blocking requirements above and reports a pass/fail result.

Until every blocking requirement exists and is validated, the repository must describe itself as having a readiness **baseline** or **plan**, not as fully production ready.

## Current baseline: necessary, not sufficient

The current default branch already provides a meaningful readiness baseline:

- namespace-first install/update under `.copilot/softwareFactoryVscode/`;
- manager-backed lifecycle and readiness vocabulary through `preflight`, `status`, and runtime verification;
- the repo-wide CI-parity path `./.venv/bin/python ./scripts/local_ci_parity.py`; and
- targeted Docker-backed lifecycle proofs where real container/image truth matters.

That baseline is necessary for internal production readiness, but it is not sufficient by itself. It does not waive any blocking requirement listed above.

## Evidence and sign-off rules

Any final internal-production sign-off must be reproducible, bounded, and retained as evidence.

At minimum, the final evidence bundle must include:

- the repo CI-parity baseline via `./.venv/bin/python ./scripts/local_ci_parity.py`;
- runtime verification against the generated effective endpoints and manager-backed readiness surface;
- the blocking Docker build parity lane;
- the blocking Docker E2E runtime proof lane;
- supported backup and restore evidence, including one recovery roundtrip proof;
- machine-readable diagnostics evidence for the supported lifecycle surface;
- links to the required runbooks and operator procedures; and
- the canonical internal production-readiness gate passing locally, in CI, and in **three consecutive clean runs**.

## Final sign-off rule

`softwareFactoryVscode` may be described as ready for **internal self-hosted production** only when all blocking requirements are implemented, the canonical internal production-readiness gate is green locally and in CI, and three consecutive clean runs have been recorded without waiving blockers.

Anything less than that is a baseline, an in-progress hardening state, or a roadmap milestone — not a final production claim.
