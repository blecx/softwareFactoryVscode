## Summary

Implement `github_access.py` Git Transport SSH probes, fulfilling ADR-019 for SSH readiness. 
This checks git remote URL, ssh-agent sock, key loaded status, and runs a bounded git@github.com probe.

## Linked issue

Fixes #595

## Scope and affected areas

- Runtime: Updated `scripts/github_access.py` to probe transport status.
- Tests: Updated `tests/test_github_access.py` with mock-based tests for Git Transport.
- Docs / manifests: None.
- GitHub remote assets: None.

## Validation / evidence

- `.venv/bin/python ./scripts/local_ci_parity.py --level merge` format and mock tests pass.
- Bounded target validation run locally.

## Cross-repo impact

- Related repos/services impacted: None.

## Follow-ups

- Next credential lanes probes will be added in further issues.
