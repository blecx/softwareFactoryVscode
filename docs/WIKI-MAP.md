# Wiki export map

This page records the stable source-to-target map for the live GitHub Wiki
projection and future resync passes. It is a planning/reference aid, not a competing authority surface.

Per
[`ADR-013-Architecture-Authority-and-Plan-Separation.md`](architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md),
accepted ADRs remain the normative architecture source, and repo file paths remain the canonical documentation source even when approved slices publish selected projections to the wiki.

## Export policy defaults

- Only material explicitly marked **Wiki-safe** below is eligible for live wiki
  publication by default. Unlisted material stays repo-only until this map is
  updated in a future approved slice.
- Wiki pages are reader-facing projections. They should link back to the source
  repository files and must not weaken the authority hierarchy documented in
  [`docs/README.md`](README.md).
- Maintainer internals, GitHub/workflow instructions, historical/archive
  material, redirect notes, and sequencing-heavy plans stay repo-only.
- Historical or superseded architecture notes stay repo-only even when they
  live under `docs/architecture/`.
- The live wiki and every future resync pass must consume this map rather than
  re-deciding publication scope ad hoc.

## Wiki-safe export targets

| Source doc or scope | Canonical wiki target | Audience | Why it is wiki-safe |
| --- | --- | --- | --- |
| [`docs/README.md`](README.md) | `Home` | All readers | Stable audience router for the documentation set. |
| [`docs/WHY-SOFTWARE-FACTORY.md`](WHY-SOFTWARE-FACTORY.md) | `Why Software Factory` | New readers / evaluators | Public intent/goals/non-goals overview without maintainer-only internals. |
| [`docs/HANDOUT.md`](HANDOUT.md) | `Operator Handout` | Operators | Guided first-run path for the supported operator workflow. |
| [`docs/INSTALL.md`](INSTALL.md) | `Install and Update` | Operators | Canonical install/update authority for day-to-day use. |
| [`docs/CHEAT_SHEET.md`](CHEAT_SHEET.md) | `Operator Cheat Sheet` | Repeat operators | Short operational command/reference surface. |
| [`docs/COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md) | `Copilot Harness Model` | Readers / maintainers | High-level explainer that stays current without turning the wiki into a plan archive. |
| [`docs/HARNESS-INTEGRATION-SPEC.md`](HARNESS-INTEGRATION-SPEC.md) | `Harness Integration Specification` | Maintainers / reference readers | Current product-level install/update ownership contract. |
| [`docs/PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) | `Internal Production Readiness Contract` | Operators / reference readers | Canonical current readiness contract. |
| [`docs/ops/MONITORING.md`](ops/MONITORING.md) | `Operator Runbook - Monitoring` | Operators | Current monitoring/runbook reference. |
| [`docs/ops/INCIDENT-RESPONSE.md`](ops/INCIDENT-RESPONSE.md) | `Operator Runbook - Incident Response` | Operators | Current incident-response runbook. |
| [`docs/ops/BACKUP-RESTORE.md`](ops/BACKUP-RESTORE.md) | `Operator Runbook - Backup and Restore` | Operators | Current backup/restore runbook. |
| [`docs/architecture/INDEX.md`](architecture/INDEX.md) | `Architecture Index` | Maintainers / reference readers | Current entrypoint that explains document classes without creating a competing authority. |
| [`docs/architecture/ADR-INDEX.md`](architecture/ADR-INDEX.md) | `Architecture ADR Catalog` | Maintainers / reference readers | Compact discovery page for the accepted ADR set. |
| Accepted `docs/architecture/ADR-*.md` entries from [`ADR-INDEX.md`](architecture/ADR-INDEX.md) | `Architecture ADR-<number> - <source title>` | Maintainers / reference readers | Current normative architecture guardrails; preserve the source ADR number and title verbatim during export. |

## Repo-only surfaces

| Source doc or scope | Export status | Why it stays repo-only |
| --- | --- | --- |
| [`README.md`](../README.md) | Repo-only | Repository landing page, current-release surface, and GitHub entrypoint; do not create a competing wiki source for release truth. |
| [`docs/WIKI-MAP.md`](WIKI-MAP.md) | Repo-only | Maintainer-facing publication-policy/control file for live wiki and future resync work. |
| [`docs/ROADMAP.md`](ROADMAP.md) | Repo-only | Active repository direction and delivery routing rather than stable operator/reference material. |
| [`docs/PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) | Repo-only | Active supporting plan and sequencing surface, not the readiness authority. |
| [`docs/WORK-ISSUE-WORKFLOW.md`](WORK-ISSUE-WORKFLOW.md) and [`docs/setup-github-repository.md`](setup-github-repository.md) | Repo-only | Repository-specific GitHub workflow and protection setup instructions. |
| `docs/maintainer/*.md` | Repo-only | Maintainer-only guardrail catalogs, workflow maps, and approval-profile internals. |
| [`docs/archive/README.md`](archive/README.md) and `docs/archive/*.md` | Repo-only | Historical/archive material preserved for traceability, not for wiki publication. |
| [`docs/CHAT-SESSION-TROUBLESHOOTING-REPORT.md`](CHAT-SESSION-TROUBLESHOOTING-REPORT.md), [`docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`](HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md), [`docs/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`](HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md), and [`docs/MCP-RUNTIME-MITIGATION-PLAN.md`](MCP-RUNTIME-MITIGATION-PLAN.md) | Repo-only | Historical redirect or closure-note surfaces that point back to the archive/history path. |
| [`docs/architecture/MULTI-WORKSPACE-MCP-ARCHITECTURE.md`](architecture/MULTI-WORKSPACE-MCP-ARCHITECTURE.md), `docs/architecture/*IMPLEMENTATION-PLAN*.md`, and [`docs/architecture/ADR-007-Multi-Workspace-and-Shared-Services.md`](architecture/ADR-007-Multi-Workspace-and-Shared-Services.md) | Repo-only | Non-normative synthesis, sequencing, or superseded history; keeping them repo-only avoids shadow-architecture or stale-plan publication. |

Live wiki publication and later resync work should consume this map rather than
re-deciding publication scope ad hoc.
