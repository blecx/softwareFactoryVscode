# Host-owned wiki truth contract

This page explains which files a future host project owns when it adopts the reusable wiki workflow stack.
It is a maintainer/reference entrypoint, not a competing authority surface.

## Authority note

Per [`ADR-013`](../architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md), accepted ADRs and canonical repository docs remain authoritative.
The live GitHub wiki remains a reader-facing projection.
The reusable `.copilot` workflow pieces must stay procedural and host-agnostic.

## Core rule

Host-owned policy/config/content are the only project-specific wiki truth surfaces.
If a detail is specific to one host project, it belongs in that host repository rather than in reusable `.copilot` instructions.

## Bootstrap before truth exists

When required host-owned wiki truth surfaces are missing, incomplete, or not yet approved, start with the reusable [`wiki-bootstrap-workflow`](../../.copilot/skills/wiki-bootstrap-workflow/SKILL.md) as the pre-truth onboarding step.
Bootstrap may scaffold or verify the starting surfaces, but it does not replace host-owned authority:

- hand off to `wiki-publication-policy-authoring` once the host can define or revise the wiki-safe versus repo-only boundary;
- hand off to `wiki-maintenance-workflow` only after the host publication policy, projection config, canonical docs, and authority docs exist and are approved.

## Ownership split at a glance

| Surface | Owned by | What it decides | What it must not become |
| --- | --- | --- | --- |
| [`docs/WIKI-MAP.md`](../WIKI-MAP.md) | Host repo | Publication policy: what is wiki-safe, what stays repo-only, and why | A second documentation index, canonical content source, or operational procedure |
| [`manifests/wiki-projection-manifest.json`](../../manifests/wiki-projection-manifest.json) | Host repo | Projection config: how approved canonical sources map to wiki pages, navigation, and lifecycle state | A substitute for publication policy or canonical content |
| Canonical `docs/*.md` pages and accepted ADRs | Host repo | Canonical content and architecture authority | Generated output or wiki-only truth |
| Live GitHub wiki pages | Generated projection | Reader-facing rendered output | An authority surface or policy source |
| [`.copilot/skills/wiki-bootstrap-workflow/`](../../.copilot/skills/wiki-bootstrap-workflow/SKILL.md), [`.copilot/skills/wiki-publication-policy-authoring/`](../../.copilot/skills/wiki-publication-policy-authoring/SKILL.md), and [`.copilot/skills/wiki-maintenance-workflow/`](../../.copilot/skills/wiki-maintenance-workflow/SKILL.md) | Reusable workflow layer | General procedure for bootstrapping starting surfaces, authoring policy, and maintaining projections across projects | A place to store one host's page inventory, policy entries, or canonical content |

## Required host-owned truth surfaces

A future host project should be able to point to all of these files without reading implementation internals:

1. `docs/WIKI-MAP.md` — the host publication boundary and repo-only rationale.
2. `manifests/wiki-projection-manifest.json` — the host projection config that consumes the approved publication boundary.
3. Canonical `docs/*.md` pages — the source content that the wiki may summarize or project.
4. Accepted ADRs or equivalent authority docs — the architectural authority that explains why the hierarchy works this way.

If any of those surfaces are missing, the fix is to author them in the host repo rather than teach `.copilot` new host-specific truth.
If any of those surfaces are missing, incomplete, or not yet approved, start with bootstrap in the host repo rather than teaching `.copilot` new host-specific truth.

## Separation rules for future hosts

- Keep publication policy separate from projection config.
- Keep projection config separate from canonical content.
- Keep canonical content separate from the live GitHub wiki projection.
- Let reusable `.copilot` skills describe how to author or maintain those files, but never let them own host-specific page inventories.
- When the host policy changes, update the host policy/config/content files first and let the live wiki follow from those sources.

## Adoption checklist

Before a future host repo publishes or refreshes wiki pages, confirm that:

- if any required truth surface is still missing or unapproved, bootstrap happens before policy authoring or live wiki maintenance;
- `docs/WIKI-MAP.md` names the host's wiki-safe and repo-only boundaries;
- `manifests/wiki-projection-manifest.json` maps only approved canonical sources;
- canonical docs already contain the wording the wiki should project;
- the live wiki is still described as a reader-facing projection;
- and reusable `.copilot` workflow assets remain free of host-specific truth.

## Use this contract when

- onboarding a future host repo to the reusable wiki workflow stack;
- deciding whether a future host must bootstrap, author policy, or maintain an existing projection;
- reviewing whether a wiki-related change belongs in host docs or in reusable `.copilot` procedure;
- or checking that policy, config, content, and live projection still respect the repo-first authority model.
