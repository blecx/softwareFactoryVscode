# GitHub wiki publishing and validation runbook

This page is a repo-only maintainer runbook for validating and publishing the live GitHub wiki.
It records the repository-specific sync procedure, not the publication policy, projection config, or canonical content.
Use this runbook only when the maintainer question is how to validate or publish the live wiki safely after approved host truth already exists.
This runbook starts only after the required host-owned truth surfaces already exist and are approved: accepted ADRs or equivalent authority docs, canonical docs, `docs/WIKI-MAP.md`, and `manifests/wiki-projection-manifest.json`.
If those surfaces are missing or unapproved, return to bootstrap or publication-policy authoring first instead of inventing truth during live wiki publishing.

## Authority note

Per [`ADR-013`](../architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md), accepted ADRs and canonical repository docs remain authoritative.
[`../WIKI-MAP.md`](../WIKI-MAP.md) decides what is wiki-safe.
[`../../manifests/wiki-projection-manifest.json`](../../manifests/wiki-projection-manifest.json) decides which approved pages are currently expected to be live and how they are routed.
The live GitHub wiki remains a reader-facing projection.

## Entry gate

Continue here only if all of the following are already true:

- `docs/WIKI-MAP.md` exists and is approved as the host publication boundary.
- `manifests/wiki-projection-manifest.json` exists and is approved as the host projection config.
- The canonical docs and accepted ADRs named by the manifest already contain the truth you intend to publish.

If any answer is `no`, stop here and return to [`HOST-WIKI-TRUTH-CONTRACT.md`](HOST-WIKI-TRUTH-CONTRACT.md), bootstrap, or publication-policy authoring instead of stretching this runbook into a truth-authoring surface.

## Use this runbook when

- validating the initial launch or any future resync pass after the required host-owned truth surfaces already exist and are approved;
- refreshing the live wiki clone under `.tmp/wiki-launch/live-wiki`;
- confirming that the current published page set still matches approved repo truth;
- or publishing already-approved wiki changes after the corresponding repo issue → PR → merge slice lands.

## Required repo-owned inputs

Read these inputs before touching the live wiki:

1. [`../WIKI-MAP.md`](../WIKI-MAP.md) — publication boundary and repo-only rationale.
2. [`../../manifests/wiki-projection-manifest.json`](../../manifests/wiki-projection-manifest.json) — the currently expected live page inventory and routing.
3. Canonical `../*.md` docs and accepted ADRs named by the manifest.
4. [`HOST-WIKI-TRUTH-CONTRACT.md`](HOST-WIKI-TRUTH-CONTRACT.md) — ownership split for policy, config, content, and projection.
5. A clean issue worktree for repo changes and a clean live wiki clone under `.tmp/wiki-launch/live-wiki`.

## Repo-first rules

- Land repo-side policy, projection-config, and canonical-content changes first.
- Do not use this runbook to bootstrap host truth or author the publication boundary from scratch.
- Treat the live wiki as output; never use it as the source of truth for what should exist.
- The root checkout on `main` remains reserved as a non-execution surface; do live issue work in dedicated worktrees.
- Keep the live wiki clone under `.tmp/wiki-launch/live-wiki` and use `.tmp/`, never `/tmp`.
- If validation exposes policy or canonical-content drift, fix the repo truth surfaces first and let the wiki follow.

## Maintainer workflow

### 1. Re-anchor repo truth

- Sync `main` and create or refresh the active issue worktree.
- Re-read `docs/WIKI-MAP.md`, `manifests/wiki-projection-manifest.json`, the canonical docs named by the manifest, and `ADR-013`.
- Confirm the repo-only runbook, publication policy, projection manifest, and canonical docs still agree on the authority model.

### 2. Refresh the live wiki clone

- Fetch and fast-forward `.tmp/wiki-launch/live-wiki` before validating or publishing.
- Confirm `git status --short --branch` is clean before editing.
- Keep the wiki clone on `master...origin/master` unless GitHub changes the wiki default branch in the future.

### 3. Validate publication boundary and page inventory

- Every published wiki page must be allowed by `docs/WIKI-MAP.md`.
- The live page set should match `manifests/wiki-projection-manifest.json` for the currently expected projection, even when `docs/WIKI-MAP.md` approves a broader future surface.
- `Home`, `_Sidebar`, and `_Footer` are shared chrome and must stay aligned with the current audience routes.
- Avoid router-to-router loops and `Home` re-entry. When `Home` or shared navigation already exposes an orientation/router page, downstream tutorial or reference pages should route readers into concrete next actions, deeper references, or canonical repo docs instead of sending them back through that same router layer.
- Repo-only surfaces such as `README.md`, `docs/maintainer/*.md`, `docs/WORK-ISSUE-WORKFLOW.md`, `docs/setup-github-repository.md`, `docs/ROADMAP.md`, `docs/PRODUCTION-READINESS-PLAN.md`, and `docs/archive/*.md` must not appear as published wiki pages or navigation destinations.

### 4. Validate page chrome

- Content pages should carry `**Canonical source:**` or `**Canonical sources:**` as appropriate.
- Shared pages may use authority-note variants such as `**Canonical source policy:**` when that better matches the page role.
- Published pages should retain a `**Projection note:**` or equivalent shared authority note.
- Sync markers are currently expressed as `**Last synced from:**`; update that field on every publish.
- When wording differs between the wiki and the repo, the repo wins.

### 5. Verify collaborators-only editing

- Confirm the repository setting `Restrict editing to collaborators only` remains enabled before publishing.
- If a future approved policy explicitly changes edit permissions, update this runbook, the relevant repo truth surfaces, and the validation notes in the same slice.

### 6. Publish safely

- Only push wiki edits that project already-approved canonical repo content.
- Direct wiki edits are for projection formatting, navigation, metadata, and bounded publication work, not for inventing new canonical truth.
- When project naming changes on a published route or page title, update `docs/WIKI-MAP.md`, `manifests/wiki-projection-manifest.json`, and every affected live wiki link in the same slice so labels, slugs, and navigation do not drift apart.
- If a needed change is really policy or content, update the repo first, merge it, and then resync the wiki.

### 7. Record bounded evidence

- Note which canonical docs were read.
- Note which wiki pages were checked or updated.
- Note the repo commit(s) used for `Last synced from`.
- Note any repo-only leak checks and collaborator-only verification.
- Note any deferred follow-up instead of silently accepting drift.

## 2026-04-29 launch validation baseline

The initial curated-launch verification established this baseline for future resync passes:

- the live wiki page inventory matched the projection manifest and stayed within the publication boundary;
- representative route and chrome checks covered `Home`, `Technical Overview`, `Day-to-Day Operator Loop`, `_Sidebar`, and `_Footer`;
- no repo-only leak hits were found for the current launch guardrails, including workflow, maintainer, roadmap, readiness-plan, and archive surfaces;
- and the current sync-marker label is `Last synced from`, so future resync passes should keep that field current instead of inventing a second marker name.
