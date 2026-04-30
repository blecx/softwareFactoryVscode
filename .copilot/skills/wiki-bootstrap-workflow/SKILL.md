---
name: wiki-bootstrap-workflow
description: "Use when bootstrapping first-time host-owned wiki truth surfaces such as docs/WIKI-MAP.md and manifests/wiki-projection-manifest.json before publication-policy authoring or wiki maintenance can begin."
---

# Wiki Bootstrap Workflow

## Objective

Provide a reusable, host-agnostic workflow for first-time host onboarding when the required host-owned wiki truth surfaces are missing, incomplete, or not yet approved.

## When to Use

- A host project does not yet have `docs/WIKI-MAP.md`.
- A host project does not yet have `manifests/wiki-projection-manifest.json`.
- One or both host-owned control surfaces exist only as drafts and are not yet authority-approved.
- The operator needs a reusable intake checklist and scaffolding procedure before publication-policy authoring or wiki-maintenance work can begin.

## When Not to Use

- Do not use this to publish, edit, or verify live GitHub wiki pages directly.
- Do not use this once the host already has approved publication policy, projection config, and canonical docs; hand off to the publication-policy-authoring skill or the maintenance workflow instead.
- Do not use this to invent host-specific page inventories, policy decisions, or canonical content inside reusable `.copilot` assets.
- Do not use this to bypass accepted ADRs or equivalent authority docs that define documentation truth.

## Role Contract

**Reusable first-time host bootstrap procedure** — owns the generic method for scaffolding host-owned wiki starting surfaces. The host project remains authoritative for the actual publication-policy entries, projection config, canonical docs, and accepted authority docs.

## Low-memory boundary shorthand

- **Publication policy** = what may go public and what stays repo-only.
- **Projection config** = where approved canonical sources land in the wiki.
- **Canonical docs + authority docs** = what the host project says and why that wording is authoritative.
- **Live GitHub wiki** = what readers see after projection.
- **Bootstrap** = the pre-truth onboarding step that gets the starting host-owned surfaces into place.
- **Next lane** = hand off to `wiki-publication-policy-authoring` for boundary decisions, or to `wiki-maintenance-workflow` only after host truth is approved.

## Required Host Inputs

Read or identify the following host-owned inputs before scaffolding any wiki control surface:

- accepted ADRs or equivalent authority docs that define documentation truth and authority boundaries;
- canonical docs or documentation indexes that will remain authoritative;
- intended audiences, routing goals, and repo-only boundaries;
- and the current state of `docs/WIKI-MAP.md` plus `manifests/wiki-projection-manifest.json`, including whether those files exist and whether they are approved.

If the host cannot identify its authority docs or canonical docs, stop and ask for the missing host context instead of inventing a convenience truth layer.

## Required Sources In This Skill

- `references/bootstrap-procedure.md`
- `references/bootstrap-guardrails.md`
- `assets/bootstrap-intake-checklist.md`
- `assets/wiki-projection-manifest-template.json`

## Workflow Summary

1. Confirm the bootstrap entry condition: one or more required host-owned wiki truth surfaces are missing, incomplete, or not yet approved.
2. Work through the intake checklist to identify the host authority docs, canonical docs, repo-only boundaries, and approval state.
3. Write down the four surface roles in host terms before editing: publication policy answers what may go public, projection config answers where approved sources land, canonical docs stay authoritative, and the live wiki stays reader-facing.
4. Scaffold a host-owned `docs/WIKI-MAP.md` by using `.copilot/skills/wiki-publication-policy-authoring/assets/wiki-map-template.md` with host-specific inputs instead of copying another host's policy or inventing final boundary decisions here.
5. Scaffold a host-owned `manifests/wiki-projection-manifest.json` by using `assets/wiki-projection-manifest-template.json` without inventing a page inventory or canonical content.
6. Record which canonical docs and authority docs will remain normative before any wiki projection work can begin.
7. Stop bootstrap once the host-owned starting surfaces exist. If the host still needs to define or revise the wiki-safe versus repo-only boundary, hand off to the publication-policy-authoring skill.
8. Hand off to the `wiki-maintenance-workflow` only after the host publication policy, projection config, canonical docs, and authority docs are present and approved.
9. Leave live wiki publishing, editing, and verification to the maintenance workflow and repo-only runbooks.

Follow the detailed bootstrap procedure in `references/bootstrap-procedure.md` and the authority/boundary rules in `references/bootstrap-guardrails.md` instead of embedding host-specific truth in this skill.

## Guardrails

- Keep project-specific wiki truth in the host repository, not in reusable skill text.
- Keep publication policy separate from projection config, canonical docs, and live wiki output.
- Treat the live GitHub wiki as a reader-facing projection, not as the authority surface.
- Bootstrap creates or verifies starting surfaces; it does not finalize host policy, write canonical content, or touch live wiki output.
- Do not ship one host's page inventory, default manifest entries, or canonical content as the reusable default for future hosts.
- Stop instead of guessing when authority inputs are missing, incomplete, or not yet approved.