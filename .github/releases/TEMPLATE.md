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

| Scope                                                          | Status                                   | Why it matters                                                           |
| -------------------------------------------------------------- | ---------------------------------------- | ------------------------------------------------------------------------ |
| Practical per-workspace baseline                               | [fulfilled / improved / unchanged]       | [what this release now supports confidently]                             |
| Shared multi-tenant promotion (ADR-008 accepted)               | [open / advanced groundwork / fulfilled] | [what is still gated, what advanced, or why it is now honestly complete] |
| Whole implementation roadmap                                   | [open / narrowed / complete]             | [how far this release moves the overall program]                         |

Keep this table crisp and honest. It should tell a reviewer, operator, or future
agent exactly what the release claims without forcing them to reverse-engineer the
roadmap from prose.

Do not mark shared multi-tenant promotion as fulfilled while its accepted
rollout criteria are still open or only partially implemented.

## Shared multi-tenant promotion gate

Use the same vocabulary in release notes and operator-facing docs:

- `open` — one or more ADR-008 rollout tracks are still incomplete, so the
  release must say what remains gated.
- `advanced groundwork` — meaningful rollout slices have landed and may be
  highlighted, but the promotion gate is still not fully satisfied.
- `fulfilled` — use only when the repository can defend the claim in code,
  tests, diagnostics, and operator guidance.

Before using `fulfilled`, verify all of the following evidence is present and
reviewed:

- explicit tenant identity is enforced end to end for promoted shared mode;
- runtime topology, verification, and operator diagnostics truthfully expose
  shared versus per-workspace behavior;
- storage, logs, metrics, and audit records are partitioned or labeled by
  tenant identity;
- cross-tenant regression coverage and Docker-backed validation prove the
  isolation contract;
- operator guidance is complete enough for repeatable day-two use; and
- a final architecture/documentation review against
  `docs/architecture/ADR-008-Hybrid-Tenancy-Model-for-MCP-Services.md` and
  `docs/architecture/MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md` confirms the
  fulfilled claim.

If any item above is still open, keep the status at `open` or `advanced
groundwork`.

## Notes for publishing

- Suggested tag: `v[version]`
- Canonical release marker: `VERSION`
- Machine-readable release source of truth: `manifests/release-manifest.json`
- Detailed release history: `CHANGELOG.md`
