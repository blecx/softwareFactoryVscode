# Archived historical note: superseded multi-workspace tenancy draft

## Status

Superseded

## Why this file still exists

This document is retained only as historical traceability for an earlier tenancy draft.

Its `ADR-007` number is intentionally retained alongside
`ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md` so older
plans, reviews, and references remain traceable without renumbering the
historical note. That duplicate numbering is historical only and does not create
two active ADR-007 authority sources.

It predates the accepted architecture split created by:

- `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`
- `ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`
- `ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md`
- `ADR-013-Architecture-Authority-and-Plan-Separation.md`

The older draft used terminology and command surfaces that are no longer current, including the legacy `X-Tenant-ID` wording and the superseded `factory_workspace.py status` lifecycle reference.

## Replacement sources of truth

- Effective endpoint generation and workspace port allocation live in the accepted `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`.
- Hybrid-tenancy promotion rules are tracked in `ADR-008`.
- Installed/running/active lifecycle semantics live in the accepted `ADR-009`.
- Document authority rules live in the accepted `ADR-013`.

## Rule

This historical note MUST NOT be used as a normative architecture source for current implementation, review, or verification work.
The accepted `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`
file remains the active ADR-007 authority source.
