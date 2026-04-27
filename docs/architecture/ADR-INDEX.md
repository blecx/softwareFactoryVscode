# ADR catalog

This page is a compact catalog of the ADRs in `docs/architecture/`.
It complements [`INDEX.md`](INDEX.md), which routes readers by document type.

## Authority note

Per [`ADR-013-Architecture-Authority-and-Plan-Separation.md`](ADR-013-Architecture-Authority-and-Plan-Separation.md), accepted ADRs are the normative architecture source for guardrails and terminology.
This catalog is a discovery aid only; it does not replace the accepted ADRs themselves.
Maintained synthesis docs, implementation plans, and historical notes remain subordinate to the accepted ADR set.

## Status summary

| ADR status | Count | How to use it |
| --- | ---: | --- |
| Accepted ADRs | 15 | Current normative architecture guardrails and terminology. |
| Superseded historical ADR notes | 1 | Historical traceability only; not a current authority source. |
| Proposed ADRs | 0 | None currently listed in `docs/architecture/`. |

## Accepted ADR catalog

| ADR | Status | What it means | Why it matters |
| --- | --- | --- | --- |
| [`ADR-001-AI-Workflow-Guardrails.md`](ADR-001-AI-Workflow-Guardrails.md) | Accepted | Makes GitHub Flow, template discipline, and local validation mandatory for AI-driven work. | Prevents workflow drift, unstructured handoffs, and direct-to-`main` shortcuts. |
| [`ADR-002-Installation-Compliance-and-Smoke-Test.md`](ADR-002-Installation-Compliance-and-Smoke-Test.md) | Accepted | Requires post-install compliance verification plus a read-only smoke prompt. | Proves the install contract before the factory claims success in a host repo. |
| [`ADR-003-Runtime-Compliance-and-Endpoint-Verification.md`](ADR-003-Runtime-Compliance-and-Endpoint-Verification.md) | Accepted | Adds a distinct, opt-in runtime verification phase for running services and endpoints. | Separates “installed correctly” from “runtime is actually alive.” |
| [`ADR-004-Host-Project-Isolation.md`](ADR-004-Host-Project-Isolation.md) | Accepted | Keeps factory runtime logic host-agnostic and free of hardcoded repo structure assumptions. | Preserves reusable harness behavior across different host repositories. |
| [`ADR-005-Strong-Templating-Enforcement.md`](ADR-005-Strong-Templating-Enforcement.md) | Accepted | Treats issue and PR templates as operational workflow contracts. | Prevents ambiguous scope, weak acceptance criteria, and incomplete PR descriptions. |
| [`ADR-006-Local-CI-Parity-Prechecks.md`](ADR-006-Local-CI-Parity-Prechecks.md) | Accepted | Requires local CI-equivalent prechecks before PR finalization. | Catches preventable failures before GitHub Actions becomes the discovery engine. |
| [`ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`](ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md) | Accepted | Makes runtime endpoints workspace-specific and generated from effective runtime metadata. | Avoids conflicting localhost contracts across concurrently installed workspaces. |
| [`ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md`](ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md) | Accepted | Defines which services stay workspace-scoped and how shared-capable services may be promoted deliberately. | Prevents blanket multi-tenant claims without isolation proof. |
| [`ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md`](ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md) | Accepted | Distinguishes `installed`, `running`, and `active` and records runtime ownership in a host-level registry. | Gives multi-workspace lifecycle one operator-visible source of truth. |
| [`ADR-010-Workspace-Cleanup-and-Registry-Reconciliation.md`](ADR-010-Workspace-Cleanup-and-Registry-Reconciliation.md) | Accepted | Defines automatic reconciliation and explicit cleanup for runtime ownership/state. | Clears stale runtime state without uninstalling the harness baseline. |
| [`ADR-011-Agent-Worker-Liveness-Contract.md`](ADR-011-Agent-Worker-Liveness-Contract.md) | Accepted | Keeps `agent-worker` as an intentional liveness placeholder instead of a real queue consumer. | Prevents reviewers and operators from assuming hidden background work execution. |
| [`ADR-012-Copilot-First-Namespaced-Harness-Integration.md`](ADR-012-Copilot-First-Namespaced-Harness-Integration.md) | Accepted | Makes `.copilot/softwareFactoryVscode/` the canonical namespaced harness surface. | Preserves clear runtime ownership without taking over host-root tooling surfaces. |
| [`ADR-013-Architecture-Authority-and-Plan-Separation.md`](ADR-013-Architecture-Authority-and-Plan-Separation.md) | Accepted | Separates accepted ADR authority from synthesis docs, plans, and derived operator docs. | Prevents shadow architecture sources from competing with accepted decisions. |
| [`ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`](ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md) | Accepted | Defines one authoritative runtime manager, snapshot, readiness, repair, and suspend/resume vocabulary. | Centralizes MCP runtime truth outside prompt logic and ad hoc status checks. |
| [`ADR-015-Quota-Governance-Contract-for-Multi-Requester-LLM-Access.md`](ADR-015-Quota-Governance-Contract-for-Multi-Requester-LLM-Access.md) | Accepted | Defines provider-facing quota authority and hierarchical budget inheritance for multi-requester LLM usage. | Prevents quota handling from turning into a shadow runtime controller. |

## Historical note on duplicate ADR-007 numbering

[`ADR-007-Multi-Workspace-and-Shared-Services.md`](ADR-007-Multi-Workspace-and-Shared-Services.md) remains in this directory as a **Superseded** historical note.
It is not part of the accepted catalog and must not be used as a current architecture authority.
Keep using the accepted [`ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`](ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md) when you need the current ADR-007 source.
