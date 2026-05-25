Resolves #483.

## Changes
- Implemented CI evidence optional checking in `scripts/production_readiness_evidence.py`.
- Updated `verify_production_signoff.py` adding `verify_ci_evidence` to validate strictly exact fields (`run_id`, `head_sha`, `job_name`, `conclusion`).
- Added robust tests in `test_production_readiness_evidence.py` and `test_verify_production_signoff.py` for CI evidence verification.

## Evidence
Local CI-parity checks passed.
Architecture decisions (ADR-013) were treated as authority.
