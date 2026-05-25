Resolves #480

## Changes

- Updates P0 handoff docs and wrappers to require preflight result evidence in handoff or closeout narration.
- Refines `.github/agents/*.md` and `.copilot/skills/*.md` discovery surfaces to require preflight evidence, maintaining them as discovery surfaces per ADR-013.
- Modifies `tests/test_ai_authority_routing.py` regression tests to lock the evidence wording.

## Evidence

- `tests/test_ai_authority_routing.py` passes successfully, validating the new wording requirements.

## Validation

```
✅ Local CI-parity checks passed with 1 warning(s).
```

*Note on Authority*: ADR-013 states that these wrapper/skill files are projections, not normative architecture sources. Thus, adding evidence requirements here adheres to the overarching design rules.
