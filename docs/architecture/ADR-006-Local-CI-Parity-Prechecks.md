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

### 2. Prechecks Must Run Before PR Finalization

- **Rule:** Before creating or finalizing a PR, the workflow MUST run the local equivalents of the current CI checks where they are executable in the local environment.
- **Rule:** For the current repository, the primary one-command workflow is:
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

### 3. Local/CI Boundary Must Be Explicit

- **Rule:** Docker image build validation remains part of CI through the canonical internal production-readiness lane (`production-readiness`) and may be optional in default local prechecks due host/runtime constraints.
- **Rule:** If Docker build parity is skipped by default, the workflow/docs MUST state that boundary explicitly and provide an opt-in local path.
- **Rule:** The documented opt-in path for local container-build parity is `./.venv/bin/python ./scripts/local_ci_parity.py --include-docker-build`.

### 4. Remote CI Is a Gate, Not a Discovery Crutch

- **Rule:** GitHub Actions remains mandatory before merge, but it MUST NOT be the first place a branch encounters known local checks.
- **Rule:** If remote CI fails due to a missed local parity check, the failure should be treated as a workflow defect, not just a one-off mistake.

### 5. Cost and Time Are Explicit Quality Concerns

- **Rule:** Local prechecks are required not only for code quality but also to reduce avoidable GitHub Actions consumption, shorten feedback loops, and lower operational cost.
- **Rule:** Future workflow simplifications MUST preserve this cost-control principle.

## Consequences

- PR readiness now includes “expected CI compatibility has been demonstrated locally.”
- Local validation becomes part of the repository’s cost-control strategy, not just a developer convenience.
- Workflow regressions that remove or weaken local prechecks can be identified as architecture violations.
