# Software Factory Integration & Regression Tests

## `run-integration-test.sh`

This script serves as a **functional regression test** for the Software Factory. It validates the core architectural constraints of this repository when used as an isolated subsystem in a parent host project.

### What it tests (regression coverage)

1. **Host Isolation (No Pollution):** Ensures the factory does not leak artifacts (like `.tmp` directories or `agent_metrics.json`) into the host project's root folder.
2. **Mount Safety:** Verifies `docker-compose` settings correctly map the target environments without accidentally over-mounting or missing the `.:/target` boundary.
3. **Internal Module Resolution:** Checks that internal python scripts remain properly namespace-scoped (`factory_runtime.agents`) and haven't regressed back to conflicting absolute imports (`from agents.`).

## Python test environment

This repository's supported contributor environment is `.venv` at the repo root.
Bootstrap it with:

```bash
./setup.sh
```

That installs:

- runtime dependencies from `factory_runtime/agents/requirements.txt`
- development and test tooling from `requirements.dev.txt`

Run the installer regression suite with the supported environment:

```bash
./.venv/bin/pytest tests/test_factory_install.py -q
```

The throwaway-target regression in `tests/test_factory_install.py` validates the real install flow into a fresh git repository, including:

- namespaced harness install into `.copilot/softwareFactoryVscode/`
- host bootstrap artifacts
- Option B workspace generation
- post-install verifier success
- non-mutating smoke prompt output contract

Default throwaway install/runtime validation should stay inside the source repository's gitignored `.tmp/` tree (for example `.tmp/throwaway-targets/`) unless a test explicitly opts into an external target. This keeps disposable targets in-workspace and avoids accidentally tainting unrelated repositories or non-repository paths.

---

## Fresh Session Handoff Prompt

If you are starting a new AI coding session (e.g., via Copilot or another Agent), copy and paste the following prompt to safely initialize the workspace context:

> "Please review the `.copilot/softwareFactoryVscode/tests/run-integration-test.sh` script to understand the expected system bounds for this project. My goal is to use this Software Factory as a completely isolated toolchain inside my main development repository.
>
> 1. First, verify that `run-integration-test.sh` still passes.
> 2. Second, start reviewing the imported code in `scripts/` side-by-side with the workspace structure (`.code-workspace.template`) and `compose/docker-compose*.yml` files.
> 3. Third, if everything works and looks correct, write a brief README section advising the host project on how to start their first task via the Factory workspace.
>
> Do not modify the VS Code or Docker configurations unless the integration test explicitly fails or points to an issue."
