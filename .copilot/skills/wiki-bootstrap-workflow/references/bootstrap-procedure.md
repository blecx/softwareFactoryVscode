# Wiki bootstrap procedure

## Input contract

Before scaffolding host-owned wiki control surfaces, gather the following inputs in order:

1. authority docs — accepted ADRs or equivalent rules that define documentation truth and authority boundaries;
2. canonical docs — the repo files and documentation indexes that remain authoritative for content;
3. current host state — whether `docs/WIKI-MAP.md` and `manifests/wiki-projection-manifest.json` are missing, incomplete, or not yet approved;
4. routing goals — intended audiences, repo-only boundaries, and the host's desired reader-facing routes.

Do not bootstrap host policy or projection config from reusable assumptions when those authority inputs are missing.

## Bootstrap entry condition

Use this workflow only when one or more required host-owned wiki truth surfaces are missing, incomplete, or not yet approved.

If the host already has an authority-approved `docs/WIKI-MAP.md`, an authority-approved `manifests/wiki-projection-manifest.json`, and canonical docs ready for projection, leave this workflow and continue with policy-authoring or maintenance instead.

## Create or update flow

1. Work through `assets/bootstrap-intake-checklist.md` and record which host-owned surfaces already exist, which are missing, and which are still unapproved.
2. Confirm the accepted ADRs or equivalent authority docs that explain why canonical repo docs remain authoritative and why the live wiki stays a reader-facing projection.
3. Confirm the canonical docs or documentation indexes that the host intends to keep authoritative after bootstrap.
4. Scaffold `docs/WIKI-MAP.md` by using `.copilot/skills/wiki-publication-policy-authoring/assets/wiki-map-template.md` with host-owned inputs rather than copied defaults.
5. Scaffold `manifests/wiki-projection-manifest.json` by using `assets/wiki-projection-manifest-template.json` with only the shared bootstrap metadata and the host's own authority wording.
6. Identify which canonical docs still need authoring or approval before any wiki projection work can begin.
7. Re-read the host-owned starting surfaces to confirm the separation among publication policy, projection config, canonical content, and live projection.

## Stop conditions and handoff

- If the host cannot identify accepted ADRs or equivalent authority docs, stop and ask for that missing authority context.
- If the host cannot identify canonical docs that remain authoritative, stop and ask for the missing canonical source set.
- If the operator is trying to publish, edit, or verify live wiki pages during bootstrap, stop and hand off to the maintenance workflow only after the host-owned truth surfaces are ready.
- If the host has the starting surfaces but still needs to define or revise the publication boundary, hand off to `wiki-publication-policy-authoring`.
- If the host has the publication policy, projection config, and canonical docs in place and authority-approved, hand off to `wiki-maintenance-workflow`.

## Evidence expectations

A bounded bootstrap change should leave a reviewable trail that states:

- which authority docs were identified;
- which canonical docs or indexes remain authoritative;
- which host-owned truth surfaces were scaffolded or repaired;
- which inputs are still missing or unapproved;
- and which workflow lane is the next approved handoff.
