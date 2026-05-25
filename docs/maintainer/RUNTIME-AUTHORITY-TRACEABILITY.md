# Runtime Authority Traceability Matrix

## Status

**Non-normative.** Per `ADR-013`, this document is a maintained traceability projection. It maps internal-production-readiness blocking requirements to their architectural authority (ADRs), implementation evidence, and derived docs. If this file conflicts with an accepted ADR, the ADR is the authoritative source.

## Traceability Matrix

| Blocking Requirement | ADR Authority | Implementation Surface | Test / Proof | Derived Docs |
| -------------------- | ------------- | ---------------------- | ------------ | ------------ |
| 1. Explicit internal-production runtime mode exists and fails closed on missing live configuration. | ADR-014 | `FACTORY_RUNTIME_MODE=production`, `verify-runtime` | `tests/test_runtime_mode.py` | `docs/PRODUCTION-READINESS.md` |
| 2. Production-required secrets and live config are validated, placeholders are rejected, and production mode does not silently downgrade to mock behavior. | ADR-014 | `scripts/verify_factory_install.py --runtime` | `tests/test_runtime_mode.py` | `docs/PRODUCTION-READINESS.md` |
| 3. Docker build parity is part of a blocking production gate. | ADR-006 | `scripts/local_ci_parity.py --level production` | `tests/test_validation_runner.py` | `docs/PRODUCTION-READINESS.md` |
| 4. At least one repeatable Docker E2E runtime proof is part of a blocking production gate. | ADR-006 / ADR-014 | `scripts/dev_stack_smoke_test.py`, `local_ci_parity.py` | `tests/test_throwaway_runtime_docker.py` | `docs/PRODUCTION-READINESS.md` |
| 5. Stateful runtime data can be backed up through a supported command with documented preconditions, metadata, and checksums. | ADR-014 | `scripts/factory_stack.py backup` | `tests/test_throwaway_runtime_docker.py` | `docs/ops/BACKUP-RESTORE.md` |
| 6. Stateful runtime data can be restored through a supported workflow with a documented recovery roundtrip proof. | ADR-014 | `scripts/factory_stack.py restore`, `resume` | `tests/test_throwaway_runtime_docker.py` | `docs/ops/BACKUP-RESTORE.md` |
| 7. Operators have machine-readable runtime diagnostics derived from the manager-backed snapshot/readiness contract. | ADR-014 | `scripts/factory_stack.py status --json` | `tests/test_factory_stack_diagnostics.py` | `docs/ops/MONITORING.md` |
| 8. Incident-response and day-two operator runbooks exist for the supported internal runtime model. | ADR-014 | Runbooks under `docs/ops/` | `tests/test_ops_runbook_contract.py` | `docs/ops/INCIDENT-RESPONSE.md` |
| 9. One canonical internal production-readiness gate aggregates the blocking requirements above and reports a pass/fail result. | ADR-006 / ADR-014 | `scripts/local_ci_parity.py --level production` | `tests/test_validation_runner_docs_contract.py` | `docs/PRODUCTION-READINESS.md` |
