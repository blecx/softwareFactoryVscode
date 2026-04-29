# Wiki maintenance procedure

## Input contract

Before touching the live wiki, gather the following host-owned inputs in order:

1. publication policy — defines which surfaces are wiki-safe and which must remain repo-only;
2. projection config or manifest — defines the source-to-target page map and shared-page responsibilities;
3. canonical source docs — the actual repo files that remain authoritative;
4. authority docs — accepted ADRs or equivalent policy docs that define the publication boundary.

Do not substitute guesses, old wiki state, or remembered page inventories for missing host inputs.

## Create or update flow

1. Build the action list from the host projection config: page title, canonical source, intended audience, and visibility state.
2. Read the canonical source doc and extract only the host-approved content for projection.
3. Render the target wiki page using host content plus the metadata rules from `wiki-metadata-rules.md`.
4. Refresh shared pages as needed:
   - `Home` for top-level discovery and audience routing;
   - `_Sidebar` for persistent navigation links;
   - `_Footer` for canonical-source reminders, contribution notes, or support links.
5. Re-check the page body against the host publication policy before publishing.
6. Publish the change and capture enough evidence to show which canonical source drove the update.

## Retire, redirect, or delete flow

1. Use the host policy and projection config to decide whether a page should be retired with a notice, redirected through navigation, or deleted outright.
2. Remove stale links from `Home`, `_Sidebar`, `_Footer`, and any cross-page navigation before or at the same time as the page retirement.
3. If the host wants a bounded transition period, replace the page with a retirement notice that points readers back to the canonical source or the replacement wiki page.
4. If the host policy says the page should disappear entirely, delete it only after navigation and inbound references have been cleaned up.
5. Re-run public-render verification after the retirement so broken navigation is caught immediately.

## Public-render verification checklist

- Confirm the page title, body, and wiki-native links render correctly on the public GitHub wiki.
- Confirm `Home`, `_Sidebar`, and `_Footer` expose the intended discovery paths and no retired links remain.
- Confirm canonical-source notes, sync markers, and projection notes are present where the host expects them.
- Confirm the published content still matches the host's canonical repo docs and does not introduce extra host-specific claims.
- Record which pages were created, updated, retired, redirected, or deleted.

## Evidence expectations

A bounded wiki-maintenance change should leave a reviewable trail:

- which host policy and projection config were read;
- which canonical source docs drove the change;
- which wiki pages changed;
- what public-render verification was performed;
- and any intentionally deferred follow-up work.
