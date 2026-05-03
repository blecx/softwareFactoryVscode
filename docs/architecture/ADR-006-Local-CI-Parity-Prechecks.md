# ADR-006: Local CI-Parity Prechecks Before Remote Validation

## Status

Accepted

## Context

GitHub Actions is the final enforcement layer for repository quality, but it is the most expensive place to discover preventable failures. When agents or operators skip local prechecks and rely on remote CI to surface basic formatting, lint, template, or integration errors, the repository burns time, compute, and GitHub billing on failures that could have been caught immediately.

`ADR-001` introduced shift-left CI in principle. We now need a sharper operational rule: the local workflow must prove expected CI compatibility before a PR is opened or handed to the merge workflow.

## Decision

We mandate **local CI-parity prechecks** before remote validation is used as a merge gate.

### 1. `.github/workflows/ci.yml` Defines the Minimum Local Validation Contract

- **Rule:** Copilot workflows that prepare or finalize a PR MUST treat `.github/workflows/ci.yml` as the source of truth for the minimum required prechecks.
- **Rule:** Workflow docs and Copilot skills MUST reference the local equivalents of CI, not merely say “run tests”.

### 2. Prechecks Must Run Before PR Finalization (The Four-Level Mirrored Validation Contract)

- **Rule:** The repository uses a canonical shared validation engine. Local execution uses the identical bundle composition and skip logic as the `ci.yml` pipeline. Local validation exists primarily to make GitHub CI pass by using the same official bundles first, with GitHub rerunning the same structure as final authority.
- **Rule:** This maintains **required-check continuity**, ensuring that all underlying prechecks are evaluated deterministically at the correct level.
- **Rule:** Before creating or finalizing a PR, the workflow MUST run the local equivalents of the current CI checks where they are executable in the local environment.
- **Rule:** The primary four-level local mirror entrypoints are invoked via `./.venv/bin/python ./scripts/local_ci_parity.py --level <level>`:
  - `focused-local`: Strict subset for fast inner-loop checks.
  - `pr-update`: PR-incremental checks.
  - `merge`: Canonical PR-readiness evidence for issue handoff.
  - `production`: Canonical internal production-readiness gate.
- **Rule:** For the current repository, the primary one-command workflow (now mapping to the four-level contract) is:
  - `./.venv/bin/python ./scripts/local_ci_parity.py`
- **Rule:** That local precheck workflow MUST cover at least:
  - `./.venv/bin/python ./scripts/verify_release_docs.py --repo-root . --base-rev <base> --head-rev HEAD`
  - `./.venv/bin/python ./scripts/factory_release.py write-manifest --repo-root . --repo-url https://github.com/blecx/softwareFactoryVscode.git --check`
  - `./.venv/bin/black --check factory_runtime/ scripts/ tests/`
  - `./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/`
  - `./.venv/bin/flake8 factory_runtime/ scripts/ tests/ --max-line-length=120 --ignore=E203,W503,E402,E731,F401,F841`
  - `./.venv/bin/pytest tests/`
  - `./tests/run-integration-test.sh`
  - `./scripts/validate-pr-template.sh ./.github/pull_request_template.md`
  - `./scripts/validate-pr-template.sh <pr-body-file>` (when applicable)

### 3. Local/CI Boundary, Explicit Exceptions, and Bounded-Runtime Rule

- **Rule:** Local-first then GitHub-confirmed semantics are explicit. Deviations where local execution skips a CI requirement (e.g. Docker-build dependencies on non-Docker hosts) must be explicitly managed exceptions codified within the shared resolver rules.
- **Rule:** **Bounded-runtime/Watchdog rule:** Validation bundles are subject to a bounded-runtime guard. Each bundle runs under a hard cap of 45 minutes (2700 seconds). A runtime timeout is a blocked state and MUST result in termination rather than indefinite polling.
- **Rule:** CI may expose diagnosable production-only jobs (for example docs-contract, docker-build parity, and runtime proofs), but the canonical internal production-readiness lane (`production-readiness`) remains the final aggregate readiness authority.
- **Rule:** Docker image build validation remains part of the required CI production path (diagnostic lanes plus canonical aggregate gate) and may be optional in default local prechecks due host/runtime constraints.
- **Rule:** If Docker build parity is skipped by default, the workflow/docs MUST state that boundary explicitly and provide an opt-in local path.
- **Rule:** The documented opt-in path for local container-build parity is `./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build`.
- **Rule:** When merge-grade confidence depends on GitHub's fresh checkout + bootstrap semantics, the local workflow MUST expose an exact parity replay path that starts from a clean git checkout/worktree, runs `./setup.sh`, and then replays the canonical gate.
- **Rule:** For the current repository, the exact local replay path for the canonical production gate is `./.venv/bin/python ./scripts/local_ci_parity.py --mode production --fresh-checkout`.

### 4. Remote CI Is a Gate, Not a Discovery Crutch

- **Rule:** GitHub Actions remains mandatory before merge, but it MUST NOT be the first place a branch encounters known local checks.
- **Rule:** If remote CI fails due to a missed local parity check, the failure should be treated as a workflow defect, not just a one-off mistake.
- **Rule:** If a local parity surface hides the actionable failure details that GitHub needs for diagnosis, that observability gap is also a workflow defect and must be fixed in the local/CI evidence path.

### 5. Cost and Time Are Explicit Quality Concerns

- **Rule:** Local prechecks are required not only for code quality but also to reduce avoidable GitHub Actions consumption, shorten feedback loops, and lower operational cost.
- **Rule:** Future workflow simplifications MUST preserve this cost-control principle.

## Consequences

- PR readiness now includes “expected CI compatibility has been demonstrated locally.”
- Local validation becomes part of the repository’s cost-control strategy, not just a developer convenience.
- Workflow regressions that remove or weaken local prechecks can be identified as architecture violations.
