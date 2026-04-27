# Documentation index

This page routes readers to the right documentation by audience and document type.
It is a navigation aid, not a competing authority source.

## Authority note

Per `ADR-013`, accepted ADRs are the normative architecture source for guardrails and terminology. Synthesis docs, implementation plans, handouts, checklists, and historical reports explain or sequence work, but they do not override accepted ADRs.

## Start here by audience

### New readers and evaluators

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

- [`WORK-ISSUE-WORKFLOW.md`](WORK-ISSUE-WORKFLOW.md) — canonical issue → PR → merge workflow.
- [`setup-github-repository.md`](setup-github-repository.md) — repository protection, branch, and CI setup guidance.
- [`HARNESS-INTEGRATION-SPEC.md`](HARNESS-INTEGRATION-SPEC.md) — install/update contract and ownership boundaries.
- [`COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md) — high-level explanation of why this repository exists and how the Factory fits into a host repo.
- [`maintainer/GUARDRAILS.md`](maintainer/GUARDRAILS.md) — maintainer-facing catalog of current guardrail families, enforcement surfaces, and where to look before changing workflow behavior.
- [`maintainer/AGENT-ENFORCEMENT-MAP.md`](maintainer/AGENT-ENFORCEMENT-MAP.md) — workflow-specific map from the major agents/prompts to the skills, templates, checkpoints, and ADRs that actually constrain them.

### Architecture and guardrails

- [`architecture/INDEX.md`](architecture/INDEX.md) — architecture directory entrypoint and authority map.
- [`architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md`](architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md) — document-authority hierarchy.
- [`architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md`](architecture/ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md) — current runtime lifecycle, prompt coordination, and resource-governance contract.

### Roadmap and active delivery tracking

- [`ROADMAP.md`](ROADMAP.md) — active/current roadmap summary that separates current direction from historical implementation plans.
- [Umbrella issue `#163`](https://github.com/blecx/softwareFactoryVscode/issues/163) — approved documentation completion program and remaining child slices.
- [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) — current shipped readiness contract.
- [`PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) — current readiness sequencing plan within the released guardrails.

### Historical and reference material

Start with the audience routes above before opening sequencing/history docs.

- [`CHAT-SESSION-TROUBLESHOOTING-REPORT.md`](CHAT-SESSION-TROUBLESHOOTING-REPORT.md) — troubleshooting and closure reference.
- [`HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`](HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md) — namespace migration sequencing history.
- [`HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`](HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md) — migration backlog and phased delivery notes.
- [`MCP-RUNTIME-MITIGATION-PLAN.md`](MCP-RUNTIME-MITIGATION-PLAN.md) — runtime mitigation planning reference.
- [`architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md`](architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md) and [`architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md`](architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md) — implementation sequencing history that remains subordinate to accepted ADRs.
