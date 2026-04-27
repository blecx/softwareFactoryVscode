# Architecture index

This file is a lightweight entrypoint for `docs/architecture/`. It helps readers
find the right document type quickly; it does not create a competing authority
source.

For a compact list of the accepted ADRs and their current statuses, use
[`ADR-INDEX.md`](ADR-INDEX.md).

## How to read this directory

1. Start with `ADR-013-Architecture-Authority-and-Plan-Separation.md` for the
   document-authority rules.
2. Use **Accepted** ADRs for normative architecture guardrails and terminology.
3. Use maintained synthesis and implementation-plan documents for explanation,
   sequencing, and historical context only.
4. If a synthesis document, plan, or historical note conflicts with an accepted
   ADR, the accepted ADR wins.

## Status map

| Document class | Status marker | Use it for | Examples |
| --- | --- | --- | --- |
| Accepted ADRs | `Accepted` | Normative architecture guardrails and terminology | `ADR-001` to `ADR-006`, `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`, `ADR-008` to `ADR-015` |
| Proposed ADRs | `Proposed` | Draft architectural direction under review; not yet normative | None currently listed in this index. |
| Superseded historical ADRs | `Superseded` | Historical traceability only; never a current authority source | `ADR-007-Multi-Workspace-and-Shared-Services.md` |
| Supporting architecture synthesis | `Maintained synthesis` | Cross-ADR explanation that defers to accepted ADRs | `MULTI-WORKSPACE-MCP-ARCHITECTURE.md` |
| Supporting implementation plans | `Proposed` or historical sequencing status | Sequencing, rollout, and hardening context within accepted ADR boundaries | `MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md`, `MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md` |

## Quick starting points

- Read [`ADR-INDEX.md`](ADR-INDEX.md) when you want a compact accepted-ADR
  catalog with one-line summaries and current status counts.
- Read `ADR-013-Architecture-Authority-and-Plan-Separation.md` first when you
  need to decide which document is authoritative.
- Read accepted `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`,
  `ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`,
  `ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md`,
  `ADR-010-Workspace-Cleanup-and-Registry-Reconciliation.md`, and
  `ADR-012-Copilot-First-Namespaced-Harness-Integration.md`, and
  `ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`
  for the current multi-workspace runtime contract.
- Read `MULTI-WORKSPACE-MCP-ARCHITECTURE.md` for a maintained, non-normative
  synthesis of how the accepted ADRs fit together.
- Read the implementation plans for sequencing history, rollout notes, and
  hardening checklists after you understand the accepted ADR set.

## ADR-007 clarification

Two files intentionally retain `ADR-007` in their filenames:

- `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md` —
  **Accepted** normative ADR.
- `ADR-007-Multi-Workspace-and-Shared-Services.md` — **Superseded** historical
  note.

The duplicate numbering is retained for historical traceability and review
archaeology. It does not mean there are two active ADR-007 authority sources.
When precision matters, cite the full accepted filename rather than bare
`ADR-007`.
