# Wiki bootstrap intake checklist

Use this checklist before creating or revising host-owned wiki truth surfaces for the first time.

## Authority prerequisites

- [ ] Accepted ADRs or equivalent authority docs are identified.
- [ ] Canonical docs or documentation indexes that remain authoritative are identified.
- [ ] Repo-only boundaries and reader-facing wiki goals are stated without copying another host's defaults.
- [ ] The approval status of `docs/WIKI-MAP.md` and `manifests/wiki-projection-manifest.json` is known.

## Host-owned starting surfaces to scaffold

- [ ] `docs/WIKI-MAP.md` will remain the host-owned publication-policy surface.
- [ ] `manifests/wiki-projection-manifest.json` will remain the host-owned projection-config surface.
- [ ] Canonical `docs/*.md` pages that may later be projected are named.
- [ ] Accepted ADRs or equivalent authority docs that approve the hierarchy are named.

## Stop conditions

- [ ] Stop if the authority docs cannot be identified.
- [ ] Stop if the canonical docs cannot be identified.
- [ ] Stop if the operator is trying to publish or edit live wiki pages during bootstrap.
- [ ] Stop if the workflow would move host-specific truth into reusable `.copilot` assets.

## Handoff decision

- [ ] Hand off to `wiki-publication-policy-authoring` once the host-owned starting surfaces exist and the publication boundary needs authoring or review.
- [ ] Hand off to `wiki-maintenance-workflow` only after the host publication policy, projection config, and canonical docs are present and authority-approved.
