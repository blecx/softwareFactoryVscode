Resolves #487.

## Changes
- Adds a fast aggregate pytest marker and bundle in `test_production_readiness_above_90_contract.py`.
- Proves language authority, fail-closed routing, signoff evidence scoring, and residue detection.
- Documents the focused command in `tests/README.md`.
- Registers custom pytest marker `above_90_readiness` in `pytest.ini`.

## Evidence
Architecture decisions (ADR-013) are strictly adhered to by treating derived docs as projections. Language validation constraints (ADR-016/ADR-017) are captured under the signoff execution bundle.

## Validation
```
1 passed in 0.93s
```
