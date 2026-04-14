# Software Factory for VS Code [version]

One short paragraph explaining what this release actually changes and what kind of
baseline it should be read as.

## Highlights

- Short highlight one
- Short highlight two
- Short highlight three

## Included enhancements

- enhancement or fix
- enhancement or fix
- enhancement or fix

## Validation

Verified with:

- targeted or full regression command/result summary
- install/update/runtime verification summary
- any release-specific migration or safety rerun

## Delivery status snapshot

| Scope | Status | Why it matters |
| --- | --- | --- |
| Practical per-workspace baseline | [fulfilled / improved / unchanged] | [what this release now supports confidently] |
| Shared multi-tenant promotion (still blocked) | [blocked / advanced groundwork / not in scope] | [what is still gated and why] |
| Whole implementation roadmap | [open / narrowed / complete] | [how far this release moves the overall program] |

Keep this table crisp and honest. It should tell a reviewer, operator, or future
agent exactly what the release claims without forcing them to reverse-engineer the
roadmap from prose.

Do not mark shared multi-tenant promotion as fulfilled while `ADR-008` remains
`Proposed` or while its rollout criteria are still open.

## Notes for publishing

- Suggested tag: `v[version]`
- Canonical release marker: `VERSION`
- Machine-readable release source of truth: `manifests/release-manifest.json`
- Detailed release history: `CHANGELOG.md`
