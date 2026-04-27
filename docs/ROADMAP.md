# Active roadmap summary

This page is the current high-level roadmap for `softwareFactoryVscode`.

It exists to separate **active direction** from **historical implementation plans**.
It is not an ADR, not a release surface, and not a replacement for issue-level
delivery tracking. Per `ADR-013`, accepted ADRs remain the authority source for
architecture guardrails and terminology.

## Current baseline

The released `2.6` story remains intact:

- namespace-first install/update under `.copilot/softwareFactoryVscode/` per
  `ADR-012`;
- the manager-backed runtime/readiness contract per `ADR-014`;
- the internal self-hosted production boundary defined in
  [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md); and
- documentation cleanup or routing work must not imply a version bump or reopen
  already shipped claims on its own.

## Active directions

### 1. Finish documentation completion without rewriting history

The currently approved documentation-completion program is tracked under
[umbrella issue `#163`](https://github.com/blecx/softwareFactoryVscode/issues/163).

The active direction for that queue is to:

- keep public entrypoints easy to navigate;
- add missing maintainer reference pages and discoverability aids;
- classify older plans, mitigation notes, and closure reports honestly before
  any archive move; and
- prepare replacement navigation before archive or wiki-export cleanup slices.

Use umbrella issue `#163`, its linked child issues, and the linked PRs for
day-to-day sequencing details rather than turning this page into a backlog dump.

### 2. Keep runtime/readiness work bounded by the current contract

Runtime/readiness hardening should continue only inside the current released
guardrails:

- [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) for the canonical
  operator-facing readiness contract;
- [`PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) for the
  bounded implementation roadmap to that contract; and
- accepted `ADR-012` and `ADR-014` for namespace and runtime authority rules.

This is roadmap guidance for refinement and verification, not permission to
claim broader hosted/SaaS scope or a second runtime authority.

### 3. Keep install/update/operator workflows explicit and repo-managed

The project continues to favor explicit, inspectable repo-managed workflow
surfaces over hidden automation. For the current model, start with:

- [`../README.md`](../README.md) and [`README.md`](README.md) for routing;
- [`WORK-ISSUE-WORKFLOW.md`](WORK-ISSUE-WORKFLOW.md) for the canonical issue →
  PR → merge lane; and
- [`HARNESS-INTEGRATION-SPEC.md`](HARNESS-INTEGRATION-SPEC.md) for install /
  update ownership boundaries.

## Deliberately not the current roadmap

This page does **not** mean the repository is reopening or weakening:

- the released `2.6` release surfaces;
- accepted ADR authority and guardrails;
- the bounded internal self-hosted production/readiness story; or
- external hosted multi-tenant SaaS ambitions that remain out of scope.

## Historical plans and sequencing notes

Historical or sequencing-heavy documents remain available when you need
traceability, but they are not the default current roadmap:

- [`HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`](HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md)
- [`HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`](HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md)
- [`MCP-RUNTIME-MITIGATION-PLAN.md`](MCP-RUNTIME-MITIGATION-PLAN.md)
- [`architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md`](architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md)
- [`architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md`](architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md)

If you are unsure whether a document is part of the current reader path or is
mainly historical/sequencing context, start with the top-level
[`../README.md`](../README.md) and the broader
[`Documentation index`](README.md) before diving into older plans.
