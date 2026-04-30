# Documentation index

This page routes readers to the right documentation by audience and document type.
It is a navigation aid, not a competing authority source.

## Authority note

Per `ADR-013`, accepted ADRs are the normative architecture source for guardrails and terminology. Synthesis docs, implementation plans, handouts, checklists, and historical reports explain or sequence work, but they do not override accepted ADRs.

## Start here by audience

### New readers and evaluators

- [`PROJECT-OVERVIEW.md`](PROJECT-OVERVIEW.md) — canonical narrative-first overview of what SoftwareFactoryVscode is trying to automate, how the AI-assisted workflow is meant to work, and where to go next.
- [`WHY-SOFTWARE-FACTORY.md`](WHY-SOFTWARE-FACTORY.md) — canonical explanation of why the project exists, who it helps, and what it explicitly is not trying to be.
- [`../README.md`](../README.md) — repository entrypoint, current release, and top-level orientation.
- [`HANDOUT.md`](HANDOUT.md) — guided overview of the Software Factory model and workflows.
- [`INSTALL.md`](INSTALL.md) — installation, update, and operator setup instructions.

### Users and day-to-day operators

- [`CHEAT_SHEET.md`](CHEAT_SHEET.md) — quick task and command reference.
- [`HANDOUT.md`](HANDOUT.md) — broader operating model and workflow guidance.
- [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) — current internal readiness contract and sign-off boundary.
- [`ops/MONITORING.md`](ops/MONITORING.md), [`ops/INCIDENT-RESPONSE.md`](ops/INCIDENT-RESPONSE.md), and [`ops/BACKUP-RESTORE.md`](ops/BACKUP-RESTORE.md) — operator runbooks for monitoring, incident handling, and recovery.

### Maintainers and workflow contributors

Wiki-related maintainer routing stays split on purpose so the index remains a first stop rather than a competing authority surface.

#### Wiki workflow first stops

For wiki-related maintainer work, keep the route compact: truth first, post-truth publishing second.

| If you need to answer... | Open first |
| --- | --- |
| Where does host-owned wiki truth live, and is bootstrap still required? | [`maintainer/HOST-WIKI-TRUTH-CONTRACT.md`](maintainer/HOST-WIKI-TRUTH-CONTRACT.md) |
| What is wiki-safe, what stays repo-only, and how do approved sources map to the live wiki? | [`WIKI-MAP.md`](WIKI-MAP.md) and [`../manifests/wiki-projection-manifest.json`](../manifests/wiki-projection-manifest.json) |
| Approved truth already exists — how do we validate or publish the live wiki safely? | [`maintainer/WIKI-PUBLISHING.md`](maintainer/WIKI-PUBLISHING.md) |

- [`WORK-ISSUE-WORKFLOW.md`](WORK-ISSUE-WORKFLOW.md) — canonical issue → PR → merge workflow.
- [`setup-github-repository.md`](setup-github-repository.md) — repository protection, branch, and CI setup guidance.
- [`maintainer/HOST-WIKI-TRUTH-CONTRACT.md`](maintainer/HOST-WIKI-TRUTH-CONTRACT.md) — future-project wiki bootstrap and ownership contract; the first stop for where host-owned truth lives, whether bootstrap is still required, and what adoption order future hosts follow.
- [`maintainer/WIKI-PUBLISHING.md`](maintainer/WIKI-PUBLISHING.md) — repo-only maintainer runbook for post-truth wiki validation, sync/publishing discipline, and collaborators-only editing checks after approved host truth already exists.
- [`WIKI-MAP.md`](WIKI-MAP.md) — stable wiki publication policy and live GitHub Wiki target map, including which current docs remain repo-only and why the wiki stays subordinate to repo authority.
- [`HARNESS-INTEGRATION-SPEC.md`](HARNESS-INTEGRATION-SPEC.md) — install/update contract and ownership boundaries.
- [`COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md) — high-level explanation of why this repository exists and how the Factory fits into a host repo.
- [`maintainer/GUARDRAILS.md`](maintainer/GUARDRAILS.md) — maintainer-facing catalog of current guardrail families, enforcement surfaces, and where to look before changing workflow behavior.
- [`maintainer/VALIDATION-BASELINE.md`](maintainer/VALIDATION-BASELINE.md) — observation-only local-vs-GitHub validation timing baseline and hotspot evidence for the phase-1 convergence work.
- [`maintainer/VALIDATION-PARITY-INVENTORY.md`](maintainer/VALIDATION-PARITY-INVENTORY.md) — observation-only inventory of parity-locked validation surfaces, exact required checks, accidental shadow policy, and CI-critical hang risks for the phase-1 convergence work.
- [`maintainer/AGENT-ENFORCEMENT-MAP.md`](maintainer/AGENT-ENFORCEMENT-MAP.md) — workflow-specific map from the major agents/prompts to the skills, templates, checkpoints, and ADRs that actually constrain them.
- [`maintainer/PROMPT-WORKFLOWS.md`](maintainer/PROMPT-WORKFLOWS.md) — maintainer-facing reference for the prompt workflow entrypoints and how they route back into the canonical workflow graph.
- [`maintainer/APPROVAL-PROFILES.md`](maintainer/APPROVAL-PROFILES.md) — maintainer-facing reference for the current approval profiles, their posture, and the source files that actually define them.

### Architecture and guardrails

- [`architecture/INDEX.md`](architecture/INDEX.md) — architecture directory entrypoint and authority map.
- [`architecture/ADR-INDEX.md`](architecture/ADR-INDEX.md) — compact accepted-ADR catalog and status summary for faster architecture discovery.
- [`architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md`](architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md) — document-authority hierarchy.
- [`architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`](architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md) — current runtime lifecycle, prompt coordination, and resource-governance contract.

### Roadmap and active delivery tracking

- [`ROADMAP.md`](ROADMAP.md) — active/current roadmap summary that separates current direction from historical implementation plans.
- [Closed umbrella issue `#163`](https://github.com/blecx/softwareFactoryVscode/issues/163) — completion record and linked child issues/PRs for the documentation-stabilization program that delivered the current structure.
- [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) — current shipped readiness contract.
- [`PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) — current readiness sequencing plan within the released guardrails.
- [`archive/README.md`](archive/README.md) — archive index for clearly historical top-level plans and reports that are no longer part of the default current reader path.

### Planning document classification matrix

Accepted ADRs and current contract documents are intentionally not listed in
this table because they remain normative authority sources rather than
roadmap/plan status entries.

| Document | Classification | Use it for |
| -------- | ---------------------- | -------------------------------------------------------------------------------------------------------------------- |
| [`ROADMAP.md`](ROADMAP.md) | Active roadmap | Current high-level direction, routing, and boundaries for active documentation/readiness work. |
| [`PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) | Active supporting plan | Current readiness sequencing within the shipped `2.6` guardrails and the scope defined by `PRODUCTION-READINESS.md`. |
| [`archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`](archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md) | Historical sequencing | Trace the delivered namespace migration and mitigation work without treating it as a current execution plan. |
| [`archive/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`](archive/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md) | Historical sequencing | Review the completed migration backlog and phased delivery notes for repository archaeology only. |
| [`archive/MCP-RUNTIME-MITIGATION-PLAN.md`](archive/MCP-RUNTIME-MITIGATION-PLAN.md) | Historical sequencing | Trace the closed runtime/readiness mitigation program and its closeout context. |
| [`architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md`](architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md) | Historical sequencing | Review runtime-manager rollout history, delivered baseline notes, and deferred-scope markers. |
| [`architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md`](architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md) | Historical sequencing | Review the fulfilled ADR-008 rollout sequencing and practical-baseline hardening history. |

### Historical and reference material

Start with the audience routes above before opening sequencing/history docs.

- [`archive/README.md`](archive/README.md) — archive index for the first pass of archived top-level plans and reports.
- [`archive/CHAT-SESSION-TROUBLESHOOTING-REPORT.md`](archive/CHAT-SESSION-TROUBLESHOOTING-REPORT.md) — troubleshooting and closure reference.
- [`archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`](archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md) — namespace migration sequencing history.
- [`archive/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`](archive/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md) — migration backlog and phased delivery notes.
- [`archive/MCP-RUNTIME-MITIGATION-PLAN.md`](archive/MCP-RUNTIME-MITIGATION-PLAN.md) — runtime mitigation planning reference.
- [`architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md`](architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md) and [`architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md`](architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md) — implementation sequencing history that remains subordinate to accepted ADRs.
