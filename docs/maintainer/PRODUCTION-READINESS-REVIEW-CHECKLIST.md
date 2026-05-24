# Production Readiness Review Checklist

> **Authority Note:** This checklist is a derived operational guide and is explicitly non-normative under [ADR-013](../architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md). It does not define new architecture rules. Accepted ADRs always take precedence.

## 1. ADR-013 Foundation Gate
- [ ] Have you read and applied `ADR-013-Architecture-Authority-and-Plan-Separation.md` before assessing readiness?

## 2. Drift Classification
For any mismatch or missing readiness requirement, classify the gap into one of the following before attempting to fix it:
- [ ] **ADR Drift:** The code or docs conflict with an accepted architecture decision (requires an ADR update or revert of the change).
- [ ] **Implementation Drift:** The code fails to match the accepted design or issue scope.
- [ ] **Validation Drift:** The tests/checks do not adequately prove the implementation is safe.
- [ ] **Derived-Doc Drift:** Operator or maintainer documentation (e.g., this checklist, readmes) no longer matches the implementation or ADRs.
- [ ] **Evidence Gap:** A claim of readiness relies on assumptions rather than concrete, reproducible evidence (e.g., CI outputs).

## 3. Pre-Merge Review
- [ ] Are all ADRs respected?
- [ ] Is the implementation complete and bounded strictly to the issue scope?
- [ ] Does local validation mirror CI and pass flawlessly?
- [ ] Have derived documents been updated to reflect the new truth?
- [ ] Is concrete evidence provided (test outputs, PR status checks) to prove readiness?
