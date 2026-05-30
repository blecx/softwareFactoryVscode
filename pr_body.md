## Summary

Add default non-secret GitHub access profile settings `FACTORY_GIT_REMOTE_TRANSPORT` and `FACTORY_GIT_SIGNING_PRIORITY` to the generated `.factory.env`, while preserving operator overrides and avoiding the generation of private key or secret material.

## Linked issue

Fixes #593

## Scope and affected areas

- Runtime: No direct runtime impact, config projection only.
- Workspace / projection: `scripts/factory_workspace.py` updated to inject defaults.
- Docs / manifests: None.
- GitHub remote assets: None.

## Validation / evidence

- `./.venv/bin/python ./scripts/local_ci_parity.py --level merge`: Pending.
- Unit tests added to `tests/test_factory_install.py`.

## Cross-repo impact

- Related repos/services impacted: None.

## Follow-ups

- None
