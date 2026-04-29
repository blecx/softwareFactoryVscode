# Wiki projection metadata rules

Use these rules to keep projected wiki pages reviewable and to remind readers that the wiki is not the canonical documentation surface.

## Canonical-source note

Each projected page should identify the host-owned canonical source that remains authoritative.

Example pattern:

> **Canonical source:** `<path/to/source-doc.md>`

## Projection note

Each projected page should state that the wiki is a reader-facing projection of repository-owned content.

Example pattern:

> **Projection note:** This page is a reader-facing projection of canonical host-repository docs.

## Sync marker

Each projected page should carry a lightweight marker showing when and from what source revision it was last refreshed.

Example pattern:

> **Sync marker:** Updated from `<source revision or commit>` on `<YYYY-MM-DD>` by `<workflow or operator>`.

## Retirement note

When a host chooses to retire a page instead of deleting it immediately, the notice should point readers to the canonical source or replacement page.

Example pattern:

> **Retired page:** This wiki page is no longer maintained. Use `<replacement page or canonical source>` for current guidance.

## Navigation hygiene rules

- `Home`, `_Sidebar`, and `_Footer` must stay aligned with the host projection config.
- Shared navigation surfaces should not advertise repo-only or non-wiki-safe content.
- Retired or deleted pages must be removed from visible navigation at the same time the content changes.
- Navigation labels should follow host terminology instead of inventing new names in the reusable skill.

## Anti-patterns

- Do not present the wiki page as the canonical source.
- Do not omit the canonical-source note when the host expects projection metadata.
- Do not hardcode one host's page inventory, URLs, or terminology as reusable defaults.
- Do not use metadata notes to smuggle in policy decisions that belong in the host publication policy or projection config.
