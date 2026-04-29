# Wiki publication-policy authoring procedure

## Input contract

Before drafting or editing a host publication-policy file, gather the following host-owned inputs in order:

1. authority docs — accepted ADRs or equivalent rules that define documentation truth and authority boundaries;
2. canonical docs — the repo files that remain authoritative for content;
3. projection config or manifest — the host-owned file that will later consume the publication policy;
4. reader goals — intended audiences, routing goals, and repo-only boundaries.

Do not author the policy from reusable assumptions when those host inputs are missing.

## Create or update flow

1. Start with a short authority note that states repo docs remain canonical and the wiki remains a projection.
2. Define export defaults that explain how unlisted content is treated.
3. Inventory candidate source docs or doc groups and classify each one as wiki-safe, repo-only, or unresolved.
4. For each wiki-safe item, record the canonical source, target wiki page, intended audience, and why it is safe to publish.
5. For each repo-only item, record why it stays out of the wiki so future maintainers do not have to rediscover the same boundary.
6. Add or update the section that explains how later wiki-maintenance work should consume the policy rather than re-deciding scope ad hoc.
7. Re-read the whole file to ensure it defines policy only and does not drift into implementation procedure or canonical content.

## Host contract shape

A strong host publication-policy file should make the following split obvious:

- publication policy decides what may be projected;
- projection config decides how approved content is routed and rendered;
- canonical docs remain the source of truth for content;
- the live wiki remains the reader-facing output.

## Review checklist

- The file names host-owned truth surfaces explicitly.
- The authority note does not suggest the wiki is canonical.
- Wiki-safe items are bounded and reviewable.
- Repo-only items include reasons, not just exclusions.
- The file does not become a second documentation index, release surface, or implementation plan.

## Evidence expectations

A bounded policy-authoring change should leave a reviewable trail:

- which host authority docs were read;
- which canonical docs were classified;
- which items became wiki-safe, repo-only, or unresolved;
- and any follow-up work required in projection config or wiki-maintenance workflows.
