# Publication boundary and authority rules

Use these rules to keep a host publication-policy file accurate, bounded, and reusable across projects.

## Authority note rules

- State clearly that canonical repository docs remain authoritative.
- State clearly that the GitHub wiki is a reader-facing projection.
- Point maintainers back to accepted ADRs or equivalent authority docs when terminology or architecture authority matters.

## Wiki-safe classification rules

A source is a strong candidate for wiki-safe publication when it is:

- stable enough for reader-facing reuse;
- useful to readers outside maintainer-only workflows;
- not primarily a sequencing plan, archive, or release-control surface;
- and safe to summarize or project without weakening the host's authority hierarchy.

## Repo-only classification rules

A source should stay repo-only when it is primarily:

- a release surface or current-release truth surface;
- a maintainer-only workflow/control document;
- a historical archive, redirect note, or superseded plan;
- a repo-internal operations/setup guide that should not be projected publicly;
- or a document whose publication would create shadow architecture or shadow policy.

## Relationship to projection config

The publication-policy file should decide whether a source may be projected.
The projection config or manifest should decide how approved sources map to wiki pages, navigation, and lifecycle state.
Do not use the publication-policy file as a substitute for projection config.

## Anti-patterns

- Do not hardcode one host's page inventory as reusable default policy.
- Do not let the publication-policy file become a second documentation index for all content.
- Do not use the file to restate the full wiki-maintenance procedure.
- Do not treat the live wiki as the proof that something is policy-approved.
- Do not omit repo-only reasons; silent exclusions rot into future ambiguity.
