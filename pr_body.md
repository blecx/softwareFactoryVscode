## Summary

Implement `github_access.py` GitHub API credential readiness probe, fulfilling the ADR-019 requirement to separate GitHub API credential lane validation from SSH/GPG.
This checks for the presence of token env variables and validates the login status smoothly with redaction of tokens.

## Linked issue

Fixes #597

## Scope and affected areas

- Runtime: Updated `scripts/github_access.py` to add `probe_github_api()`. Added `factory_runtime.secret_safety` dependency.
- Tests: Updated `tests/test_github_access.py` to mock `subprocess.run` and test the return format of `probe_github_api()` ensuring tokens are redacted.
- Docs / manifests: None.
- GitHub remote assets: None.

## Validation / evidence

- `.venv/bin/python ./scripts/local_ci_parity.py --level merge` format and mock tests pass.
- Bounded target validation run locally.

## Cross-repo impact

- Related repos/services impacted: None.

## Follow-ups

- Further refinements to credential isolation as per ADR-019 if required.
