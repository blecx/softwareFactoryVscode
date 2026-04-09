# ADR-002: Installation Compliance Verification & Non-Mutating Smoke Test

## Status

Accepted

## Context

`softwareFactoryVscode` is installed into other repositories as a hidden-tree subsystem. A clone + bootstrap sequence alone is not enough to prove that the host repository is actually ready for VS Code usage. We need a strict, machine-executable compliance step that confirms the install contract is satisfied immediately after installation or update.

We also need a human-friendly smoke-test prompt that can be used in VS Code to demonstrate that the installed workspace is visible and inspectable by the agent without mutating the target repository.

## Decisions

### 1. Mandatory Post-Install Compliance Verification

Every install or update MUST run a dedicated compliance script after bootstrap and before reporting success.

- **Rule:** The installer MUST invoke `scripts/verify_factory_install.py` automatically.
- **Rule:** If compliance verification fails, the install/update MUST be reported as failed.
- **Rule:** The verifier MUST be read-only with respect to the target repository.

### 2. Verification Scope is the Installation Contract

The compliance script MUST verify the install contract rather than relying on informal operator inspection.

- **Rule:** Verify the presence of `.softwareFactoryVscode/` as a hidden-tree git checkout.
- **Rule:** Verify host-side artifacts such as `.copilot/softwareFactoryVscode/.factory.env`, `.copilot/softwareFactoryVscode/lock.json`, and `.copilot/softwareFactoryVscode/.tmp/`.
- **Rule:** Verify the Option B workspace entrypoint (`software-factory.code-workspace`) unless explicitly skipped.
- **Rule:** Verify `.gitignore` contains the required factory isolation entries unless explicitly skipped.

### 3. Non-Mutating Smoke Prompt is Part of the Install UX

The install workflow MUST provide a smoke prompt that helps the operator confirm the VS Code experience without changing the target repository.

- **Rule:** The verifier MUST print a non-mutating smoke prompt on successful verification.
- **Rule:** The smoke prompt MUST explicitly forbid file mutations and state-changing commands.
- **Rule:** The smoke prompt MUST ask for PASS/FAIL evidence against the installed workspace contract.

## Consequences

- Successful installation now means: clone/update, bootstrap, and compliance verification all passed.
- Operators get an immediate read-only prompt to confirm that the VS Code workspace experience looks correct.
- Install/update behavior becomes stricter and less ambiguous, especially for repeated rollout into multiple repositories.
