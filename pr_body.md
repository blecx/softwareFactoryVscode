## Summary
This implements the feature to route execution through the model-fit policy as required by the execution constraints. It implements model tier resolution and integrates it within `RouterAgent`.

## Linked issue
Fixes #632

## Scope and affected areas
- Added `factory_runtime/agents/model_selection_policy.py`
- Added `tests/test_model_selection_policy.py`
- Updated `factory_runtime/agents/router_agent.py`

## Validation / evidence
Targeted unit tests for model selection policy pass. Focused tests (`test_model_selection_policy.py`) for fitness and fallback actions successful. Full `test_regression.py` suite passed with no regressions.
NOTE: This issue unlocks the next issue (audit/tool selection work).

## Cross-repo impact
None.

## Follow-ups
Unlocks the next step in model capability selection downstream.
