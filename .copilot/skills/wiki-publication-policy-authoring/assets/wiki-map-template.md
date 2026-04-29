# Wiki export map

This page records the host-owned publication boundary for later GitHub Wiki projection work.
It is a policy/control surface, not a competing authority source.

Per `<accepted ADR or authority doc>`, canonical repository docs remain authoritative even when selected material is later projected to the wiki.

## Export policy defaults

- Only material explicitly marked **Wiki-safe** below is eligible for later wiki projection by default.
- Unlisted material stays repo-only until the host updates this map.
- Wiki pages are reader-facing projections that must link back to canonical repo docs.
- Maintainer-only internals, historical/archive material, release surfaces, and sequencing-heavy plans stay repo-only unless the host explicitly approves otherwise.

## Wiki-safe export targets

| Source doc or scope | Canonical wiki target | Audience | Why it is wiki-safe |
| --- | --- | --- | --- |
| [`docs/example.md`](example.md) | `Example Page` | Example readers | Short reason why the host considers it safe to project. |

## Repo-only surfaces

| Source doc or scope | Export status | Why it stays repo-only |
| --- | --- | --- |
| [`README.md`](../README.md) | Repo-only | Example reason why this surface must remain canonical in the repo. |

Later wiki-maintenance work should consume this map rather than re-deciding publication scope ad hoc.
