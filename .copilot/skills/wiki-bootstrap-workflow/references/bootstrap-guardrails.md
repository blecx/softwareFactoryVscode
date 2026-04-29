# Wiki bootstrap guardrails

Use these rules to keep first-time host wiki onboarding reusable, bounded, and subordinate to host-owned truth.

## Authority input rules

- Require accepted ADRs or equivalent authority docs before scaffolding host-owned wiki control surfaces.
- Require canonical docs or documentation indexes that will remain authoritative after bootstrap.
- Require the operator to state whether `docs/WIKI-MAP.md` and `manifests/wiki-projection-manifest.json` are missing, incomplete, or not yet approved.
- Stop when authority ownership or approval state is unknown instead of inventing a convenience truth layer.

## Host-owned surface rules

- `docs/WIKI-MAP.md` remains the host-owned publication-policy surface.
- `manifests/wiki-projection-manifest.json` remains the host-owned projection-config surface.
- Canonical `docs/*.md` pages and accepted ADRs remain the host-owned authority and content surfaces.
- Reusable `.copilot` assets may provide templates, checklists, and procedure, but they must not become the storage location for one host's page inventory, approval decisions, or canonical content.

## Handoff rules

- Bootstrap stops once the required host-owned starting surfaces exist and the next step is clearly policy authoring or maintenance.
- Use `wiki-publication-policy-authoring` when the host still needs to define or revise the wiki-safe versus repo-only boundary.
- Use `wiki-maintenance-workflow` only after the host publication policy, projection config, and canonical docs are present and authority-approved.
- Leave live wiki publishing, editing, and verification to the maintenance workflow plus repo-only runbooks.

## Anti-patterns

- Do not copy another host's page inventory, manifest entries, or canonical content into reusable bootstrap assets.
- Do not treat a scaffold template as the host's approved policy or approved projection config.
- Do not collapse publication policy, projection config, canonical content, and live projection into one convenience file.
- Do not use the live wiki as proof that the host policy is complete.
- Do not let reusable `.copilot` assets claim ownership of canonical docs or live wiki state.
