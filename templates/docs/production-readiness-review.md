# Production Readiness Review

## Validation Rules
> **WARNING**: A docs-only assessment is **INVALID**. You must prove readiness using actual implementation, validation loops, and explicit authority evidence.

**Pre-Requisite Gate**:
- [ ] `adr_013_loaded`: I confirm that ADR-013 is loaded and I am enforcing the required document-authority hierarchy and authority-chain.

## Authority-Chain / Architecture Sources
- **ADR sources**: (List accepted ADRs that govern this feature/change)

## Implementation Evidence
- **Implementation sources**: (List the real source files, pull requests, and commit SHAs that provide the implementation)

## Validation Evidence
- **Validation sources**: (List local/CI test outputs, reproduction steps, or parity reports that verify the implementation works)

## Documentation Alignment
- **Derived docs checked**: (List operator docs, handouts, skills, or wikis that were reviewed/updated for consistency)
- **Mismatch classification**: (Is there drift between the implementation and architecture? Describe any intention to update ADRs vs update derived docs)

## Final Assessment

- **Signoff evidence (Required for >90% gate)**: (Must cite the explicit durable signoff artifact path or GitHub CI status that clears this for merge/production)
- **Aggregate Readiness (Required for >90% gate)**: (Must cite the output of `scripts/production_readiness_evidence.py --strict-verification` proving a passing score block and at least a 3-run green streak)
- **Traceability (Required for >90% gate)**: (Confirm that there are no "Evidence gap" values across all required traceability requirements)
- **Runtime Proof (Required for >90% gate)**: (Confirm presence of runtime diagnostics and operational runbook proof covering the capability space)
- **ADR-016/ADR-017 Authority (Required for >90% gate)**: (Must cite boundary validation compliance with accepted ADR-016/017 rules)
- **Fail-closed preflight (Required for >90% gate)**: (Must cite proof of fail-closed preflight verification)
- **Workflow residue (Required for >90% gate)**: (Confirm there is no stale workflow residue via tests or GitHub truth check)
- **Blockers**: (Any remaining issues blocking immediate production rollout)

