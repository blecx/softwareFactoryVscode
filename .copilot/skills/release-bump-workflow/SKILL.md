---
name: release-bump-workflow
description: Canonical release bump workflow for `softwareFactoryVscode`. Use when cutting or publishing a release, bumping `VERSION`, updating current-release surfaces, verifying Definition of Done and quality metrics, or checking that historical release references do not leak into public current-release docs.
---

# Release bump workflow

## Objective

Provide one canonical, `.copilot`-owned definition for cutting a release in
`softwareFactoryVscode` without leaving stale prior-version artifacts on the
current-release surfaces.

## Canonical ownership

- The canonical release workflow contract lives under
  `.copilot/skills/release-bump-workflow/`.
- Release notes are source-controlled under `.github/releases/`; GitHub's
  published release must be derived from the checked-in notes rather than from
  ad-hoc UI-only edits.
- Historical release files such as `.github/releases/v2.5.md` and changelog
  sections for earlier versions remain legitimate historical artifacts and MUST
  NOT be rewritten as part of a new release bump.

## Current-release surfaces

The active release is defined by the synchronized state of all of the following:

- `VERSION`
- `README.md` `## Current Release`
- `CHANGELOG.md`
- `.github/releases/v<version>.md`
- `manifests/release-manifest.json`
- the published GitHub tag/release for `v<version>`

Any prior-version string on those current-release surfaces is a release defect,
even if the older version still appears correctly in historical files.

## Definition of done

The release workflow is done only when all of the following are true:

- all current-release surfaces point at the same version
- `README.md` `## Current Release` references the matching checked-in release
  notes file
- `CHANGELOG.md` contains the dedicated `## [<version>]` section
- `.github/releases/v<version>.md` contains the required delivery-status
  snapshot and publish notes
- `manifests/release-manifest.json` reports the same `version_core` in
  `latest` and `channels.stable`
- post-commit `scripts/verify_release_docs.py` passes against `HEAD^..HEAD`
- post-commit `scripts/factory_release.py write-manifest --check` passes
- the release PR is merged to `main`
- the `v<version>` tag and GitHub release are published from the committed
  artifacts

## Quality metrics

The release workflow MUST evaluate and report these metrics:

- current-release surface consistency: 100%
- README current-release sync: 100%
- machine-readable metadata consistency: 100%
- release guardrail pass rate: 100%
- historical-artifact isolation: 100%

## Execution steps

1. Resolve the target version and read the existing release surfaces before
   editing.
2. Update `VERSION`, `README.md` `## Current Release`, `CHANGELOG.md`,
   `.github/releases/v<version>.md`, and `manifests/release-manifest.json`.
3. Check that historical version references remain only in explicit release
   history files/sections and do not leak into current-release surfaces.
4. Commit the release bump in a dedicated commit so the post-commit release
   checks can compare `HEAD^..HEAD`.
5. Run `scripts/verify_release_docs.py` and
   `scripts/factory_release.py write-manifest --check` against the committed
   release bump.
6. Run the required release validation commands for the release scope.
7. Open and merge the release PR.
8. Create and publish the `v<version>` tag and GitHub release from the
   checked-in notes.
9. Re-audit the public README / current-release surfaces after publication.

## Validation contract

Minimum guardrail validation:

```text
./.venv/bin/python ./scripts/verify_release_docs.py --repo-root . --base-rev HEAD^ --head-rev HEAD
./.venv/bin/python ./scripts/factory_release.py write-manifest --repo-root . --repo-url https://github.com/blecx/softwareFactoryVscode.git --check
```

Recommended release-grade validation:

```text
./.venv/bin/python ./scripts/local_ci_parity.py --mode production
```

## Failure modes to prevent

- `VERSION` updated while `README.md` still advertises the prior release
- release notes published for the new version while `README.md` still links to
  the prior release-notes file
- machine-readable release metadata updated while human-facing current-release
  docs remain stale
- historical references to older releases mistaken for active-release defects