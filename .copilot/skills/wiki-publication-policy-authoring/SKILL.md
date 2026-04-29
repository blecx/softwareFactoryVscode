---
name: wiki-publication-policy-authoring
description: "Use when creating, reviewing, or updating a host-owned wiki publication policy such as docs/WIKI-MAP.md while keeping project-specific truth in the host repository."
---

# Wiki Publication Policy Authoring

## Objective

Provide a reusable, host-agnostic workflow for authoring and maintaining host-owned wiki publication policy files that define what may be published to a GitHub wiki and what must remain repo-only.

## When to Use

- A host project needs to create a first publication-policy file such as `docs/WIKI-MAP.md`.
- An existing host publication-policy file needs to be expanded, clarified, or corrected.
- The operator needs a reusable checklist for classifying host docs as wiki-safe or repo-only.
- The host needs guidance on how publication policy relates to projection config, canonical docs, and live wiki output.

## When Not to Use

- Do not use this to publish or edit live wiki pages directly.
- Do not use this as the first step when `docs/WIKI-MAP.md` and/or `manifests/wiki-projection-manifest.json` are missing, incomplete, or not yet approved; start with `wiki-bootstrap-workflow` instead.
- Do not use this to invent host-specific page inventories inside `.copilot`.
- Do not use this to treat the publication policy file as canonical content or implementation procedure.
- Do not use this to bypass accepted ADRs or equivalent authority docs that define documentation truth.

## Role Contract

**Reusable publication-policy authoring procedure** — owns the general method for defining a host project's wiki publication boundary. The host project remains authoritative for the actual policy entries, projection config, canonical docs, and accepted authority documents.

## Required Host Inputs

Read the host-owned truth surfaces before drafting or editing the publication policy:

- the host's canonical docs and current documentation index;
- the host's accepted ADRs or equivalent authority docs;
- any existing projection config or manifest that will consume the policy;
- and the host's intended audiences, routing goals, and repo-only constraints.

If the host cannot identify those inputs, stop and ask for the missing host context instead of inventing a publication boundary from reusable defaults.

If the host is still scaffolding those starting surfaces for the first time, hand off to `wiki-bootstrap-workflow` before returning here.

## Required Sources In This Skill

- `references/policy-authoring-procedure.md`
- `references/publication-boundary-rules.md`
- `assets/wiki-map-template.md`

## Workflow Summary

1. Read the host's authority docs and canonical documentation surfaces.
2. Inventory candidate docs or doc groups that might be published.
3. Classify each item as wiki-safe, repo-only, or unresolved.
4. Map wiki-safe sources to canonical wiki targets without turning the map into a second source of truth.
5. Record repo-only surfaces and explain why they stay out of the wiki.
6. Define how the policy relates to host projection config and canonical docs.
7. Review the file for authority wording, anti-patterns, and host-specific accuracy.
8. Leave live wiki publication to the maintenance workflow once the host policy is in place.

Follow the detailed authoring procedure in `references/policy-authoring-procedure.md` and the classification/authority rules in `references/publication-boundary-rules.md` rather than embedding host-specific policy defaults here.

## Guardrails

- Keep project-specific publication truth in the host repository, not in reusable skill text.
- Treat the publication-policy file as a host-owned control surface, not as canonical content.
- Require the host to separate publication policy from projection config and from canonical docs.
- Keep the live wiki reader-facing and repo docs authoritative.
- Do not ship one host's wiki-safe page inventory as a reusable default for every future project.
