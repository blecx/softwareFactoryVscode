Resolves #484.

## Changes
- Extend production readiness score checker to read `green_streak_count`.
- Fail readiness when count is below 3.
- Blocker correctly explains the three-run rule ("Production gate requires 3 consecutive clean signoff runs.").
- Keep current production gate behavior unchanged.
- Covered all configurations in unit testing.

## Evidence
- Local unit tests pass.
- ADR-013 applied first and respected throughout the scope.
- ADR-016 / ADR-017 ownership boundaries respected.

## Validation
```
14 passed in 0.21s
```
```
Local CI-parity checks passed.
```
