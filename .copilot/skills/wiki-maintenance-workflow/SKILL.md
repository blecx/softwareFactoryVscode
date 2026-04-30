---
name: wiki-maintenance-workflow
description: "Use when creating, updating, retiring, or verifying a GitHub wiki projection while keeping host-owned publication policy, projection config, and canonical docs authoritative."
---

# Wiki Maintenance Workflow

## Objective

Provide a reusable, host-agnostic workflow for creating, updating, retiring, and verifying GitHub wiki pages as reader-facing projections of canonical host-repository documentation.

## When to Use

- A host project needs to create or update GitHub wiki pages from canonical repository docs.
- Shared navigation pages such as `Home`, `_Sidebar`, or `_Footer` need to be added or refreshed.
- Existing wiki pages need to be retired, redirected, or deleted because the host policy or source docs changed.
- The operator needs a repeatable verification checklist for public wiki render, navigation integrity, and projection metadata.

## When Not to Use

- Do not use this to invent or rewrite the host project's publication policy.
- Do not use this when `docs/WIKI-MAP.md` and/or `manifests/wiki-projection-manifest.json` are missing, incomplete, or not yet approved; start with `wiki-bootstrap-workflow` instead.
- Do not use this when the host has not defined the publication boundary, projection config, and canonical source docs yet.
- Do not use this to treat the wiki as canonical source material.
- Do not use this to bypass the repository's normal issue → PR → merge workflow for host changes.

## Role Contract

**Reusable wiki-maintenance procedure** — owns the generic operational mechanics for GitHub wiki projection work. The host project remains authoritative for project-specific publication policy, projection config, source-document inventory, and canonical content.

## Low-memory boundary shorthand

- **Bootstrap** = create or verify the starting host-owned surfaces when they are missing, incomplete, or unapproved.
- **Publication policy** = what may go public and what stays repo-only.
- **Projection config** = where approved canonical sources land in the wiki.
- **Canonical docs + authority docs** = what the host project says and why that wording is authoritative.
- **Live GitHub wiki** = what readers see after projection.
- **This skill** = update live wiki output from approved host truth, once the boundary and source docs already exist and are approved.

## Required Host Inputs

Read all host-owned truth surfaces before changing any wiki page:

- the host-owned publication policy that decides what is wiki-safe and what stays repo-only;
- the host-owned projection config or manifest that maps canonical source docs to wiki targets;
- the canonical host docs that will be projected or referenced;
- and the host's accepted ADRs or equivalent authority docs that define publication and authority boundaries.

If any required host input is missing or ambiguous, stop and ask the host to author or fix it instead of guessing.

If the host still needs to create those first host-owned starting surfaces, hand off to `wiki-bootstrap-workflow` before returning here.

## Required Sources In This Skill

- `references/maintenance-procedure.md`
- `references/wiki-metadata-rules.md`
- `assets/shared-pages/Home.md`
- `assets/shared-pages/_Sidebar.md`
- `assets/shared-pages/_Footer.md`
- `assets/retired-page-notice.md`

## Workflow Summary

1. Confirm the lane really is maintenance: the host publication policy, projection config, canonical docs, and authority docs already exist and are approved.
2. Read the host publication policy and authority docs.
3. Read the host projection config or manifest.
4. Read the canonical source docs named by the host.
5. Classify each target as create, update, keep, retire, redirect, or delete.
6. Apply the appropriate shared-page or page-body template without inventing host-specific truth.
7. Update navigation surfaces (`Home`, `_Sidebar`, `_Footer`) when the host policy says a visible route changed.
8. Add or refresh canonical-source notes, sync markers, and projection notes.
9. Verify the rendered wiki pages publicly and confirm navigation integrity.
10. Record bounded verification evidence so the host can review what changed.

Follow the detailed mechanics in `references/maintenance-procedure.md` and the metadata constraints in `references/wiki-metadata-rules.md` rather than restating those rules ad hoc.

## Guardrails

- The live GitHub wiki is a reader-facing projection, not the canonical source of documentation truth.
- Never infer a page set, navigation tree, or export boundary from memory when the host policy or projection config is missing.
- Maintenance consumes approved host truth; it does not invent missing policy, projection scope, or canonical wording.
- Keep reusable procedure in this skill and keep project-specific truth inside the host repository.
- Update or remove navigation links when retiring pages so stale discovery paths do not linger.
- Prefer small, reviewable wiki changes that remain traceable back to canonical host docs.
