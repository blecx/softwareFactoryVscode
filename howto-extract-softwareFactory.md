# howto-extract-softwareFactory

## Purpose

This document is the **step-by-step extraction workflow** for turning the reusable Software Factory capabilities currently living inside `maestro` into a standalone repository named `softwareFactoryVscode`.

It is intentionally operational.

Preserved migration goal line (kept verbatim):

> Always keept the goal, that we like to move the software factory to a new project taking all of its capability, but nothing from maestor.

Use it when the goal is to:

- extract the Software Factory from `maestro`,
- carry over the full local runtime and developer environment,
- carry over the required external dependencies and remote GitHub configuration,
- remove Maestro-specific coupling,
- and leave the result installable, testable, and maintainable.

This document complements:

- `softwareFactoryVscode.md`
- `externalDevendenciesSoftwareFactory.md`
- `SoftwareFactoryVsocdeTestsuite.md`

If those documents define the contract, this file defines **how to execute the extraction** without improvisation.

---

## Target outcome

By the end of this workflow, you must have:

1. a standalone GitHub repository named `softwareFactoryVscode`,
2. the reusable factory runtime and developer tooling extracted from `maestro`,
3. the full required local environment contract documented and bootstrappable,
4. the full required external dependency and remote GitHub configuration documented and reproducible,
5. validation proving the extracted package works in a blank host repository.

---

## What this workflow extracts

The extraction must carry over the **factory**, not the Maestro application.

### Extract

- MCP/runtime services that belong to the factory
- Dockerfiles and compose files for those services
- runtime orchestration scripts
- bootstrap and projection logic
- hidden-tree bootstrap and isolation logic
- `.copilot/` configuration and skills that are part of the reusable factory
- `.github/agents/` wrappers that belong to the reusable workflow layer
- `.vscode/` workspace behavior required for the factory workflow
- documentation required to install, operate, upgrade, and validate the package
- GitHub workflow/template/policy artefacts needed to reproduce remote guardrails

### Do not extract

- `apps/api/`
- Maestro-specific application UI/frontend artefacts
- Maestro product logic
- hardcoded Maestro repo defaults
- Maestro-specific queue or workflow logic that is not generally reusable

---

## Extraction principles

Keep these rules true throughout the entire workflow.

1. **Runtime and meta tooling must stay separated.**
2. **No host-global `/tmp` usage for package-controlled artefacts.** Use repo-local `.tmp/` instead.
3. **No hidden dependency on the source repo after extraction.**
4. **No Maestro-specific naming may remain unless explicitly cited as source history.**
5. **Remote GitHub behavior must be treated as part of the environment**, not as an afterthought.
6. **The package must be usable in a blank host repo** through documented bootstrap steps.
7. **External dependencies must be classified and documented**, not rediscovered later by pain.
8. **Take all reusable software-factory capability, but nothing from `maestro`.** If an artifact is not reusable factory capability, do not extract it.

---

## Prerequisites before starting

Before performing the extraction, confirm the operator machine has:

- `git`
- `gh` authenticated against GitHub
- Python available for package scripts
- Docker and Docker Compose
- Node.js if any bundled extension or JS-based tooling still requires it
- VS Code if workspace parity needs to be verified during extraction

Also confirm you have permissions to:

- create a new GitHub repository
- configure repository settings
- configure branch protection and required checks
- configure labels and templates
- configure repository secrets and variables if needed

---

## Phase 0 — Freeze the source and collect inputs

### Step 0.1 — Identify the source baseline

Choose the exact source ref from `maestro` that the extraction will use.

Record:

- repository: `blecx/maestro`
- branch or commit SHA used as source baseline
- extraction date
- operator

### Step 0.2 — Gather the three source contracts

Treat these three files as required input:

- `softwareFactoryVscode.md`
- `externalDevendenciesSoftwareFactory.md`
- `SoftwareFactoryVsocdeTestsuite.md`

### Step 0.3 — Create an extraction working log

Create a working log for the extraction that records:

- included paths
- excluded paths
- renamed paths
- deleted Maestro-specific coupling
- unresolved decisions
- external dependency findings

Expected output:

- a durable extraction notebook or markdown log under `.tmp/` or `docs/working/`

---

## Phase 1 — Inventory what belongs to the factory

### Step 1.1 — Build the include inventory

From `maestro`, inventory all reusable factory assets.

Minimum categories:

- `.vscode/`
- `.copilot/config/`
- `.copilot/skills/`
- `.github/agents/`
- factory-relevant `scripts/`
- factory-relevant `agents/`
- factory-relevant `apps/mcp/`
- `apps/approval_gate/`
- `apps/mock_llm_gateway/` if kept
- `docker/`
- root `docker-compose*.yml`
- reusable `configs/`
- reusable tests and validation utilities

### Step 1.2 — Build the exclude inventory

Explicitly classify paths that must not be carried over.

Minimum exclusions:

- `apps/api/**`
- Maestro product-specific docs and templates
- frontend artefacts tied only to the Maestro product
- `_external/maestro-Client/**`
- scripts that only serve Maestro-specific issue queue management unless they are generalized

### Step 1.3 — Create the extraction manifest

Create a machine-readable manifest recording for every candidate path whether it is:

- copied as-is,
- copied then adapted,
- split,
- renamed,
- or excluded.

Expected output:

- `manifests/extraction-manifest.json`
- `docs/EXTRACTION-SOURCE-MAP.md`

---

## Phase 2 — Create the standalone destination repo

### Step 2.1 — Create the new repository

Create a new GitHub repository named:

- `softwareFactoryVscode`

Initialize it with:

- branch `main`
- README stub
- no application-specific baggage

### Step 2.2 — Create the target folder layout

Create the target structure defined by `softwareFactoryVscode.md`, including at least:

- `.vscode/`
- `.copilot/`
- `.github/`
- `compose/`
- `configs/`
- `docker/`
- `docs/`
- `factory_runtime/`
- `hooks/`
- `manifests/`
- `scripts/`
- `templates/`
- `tests/`

### Step 2.3 — Add the contract docs first

Copy in or author these docs immediately so the repo has a clear contract from day one:

- `softwareFactoryVscode.md`
- `externalDevendenciesSoftwareFactory.md`
- `SoftwareFactoryVsocdeTestsuite.md`
- `howto-extract-softwareFactory.md`

Expected output:

- destination repo exists with the baseline structure and governing docs

---

## Phase 3 — Copy the factory assets

### Step 3.1 — Copy developer/meta assets

Copy the reusable meta layer:

- `.vscode/settings.json`
- `.vscode/tasks.json`
- `.vscode/extensions.json`
- selected `.vscode/extensions/**` only if intentionally retained
- `.copilot/config/**`
- `.copilot/skills/**`
- `.github/agents/**`
- reusable hooks
- reusable setup/projection scripts

### Step 3.2 — Copy runtime assets

Copy the reusable runtime layer:

- factory-relevant `agents/**`
- factory-relevant `apps/mcp/**`
- `apps/approval_gate/**`
- `apps/mock_llm_gateway/**` if part of the chosen package profile
- Dockerfiles in `docker/**`
- compose files in root `docker-compose*.yml`
- reusable default configs

### Step 3.3 — Copy tests and validators

Carry over or rehome the tests that prove:

- runtime/meta separation
- neutrality
- runtime startup
- install/bootstrap correctness
- environment consistency

Expected output:

- extracted assets exist in the standalone repo in roughly correct locations, even if still unneutralized

---

## Phase 4 — Neutralize Maestro-specific coupling

This is the phase where the factory stops smelling like its parent repo.

### Step 4.1 — Rename package identity

Replace package identity references such as:

- `maestro`
- `blecx/maestro`
- Maestro image names
- Maestro network names
- Maestro CLI text

Allowed exception:

- historical references in source-map or migration docs

### Step 4.2 — Remove application coupling

Remove or rewrite references to:

- `maestro-Client`
- `_external/maestro-Client`
- backend/client split assumptions that are not universally valid

### Step 4.3 — Neutralize repo defaults

Replace default repo assumptions such as:

- `YOUR_ORG/YOUR_REPO`
- issue/PR defaults tied to the source repo
- label sets that are Maestro-specific rather than generally reusable

### Step 4.4 — Remove `/tmp` dependencies

Replace package-controlled host temp usage with:

- `.tmp/softwareFactoryVscode/...`
- `/factory/tmp/...` for internal container-only ephemeral state

Expected output:

- neutrality scans pass or have only tracked exceptions

---

## Phase 5 — Rebuild the runtime boundary

### Step 5.1 — Separate runtime from meta tooling

Ensure runtime code does not depend on:

- `.copilot/`
- `.github/agents/`
- `.vscode/`

### Step 5.2 — Move toward `/factory` and `/target`

Refactor runtime packaging so that:

- factory-owned runtime is mounted or baked at `/factory`
- the consuming host repo is mounted at `/target`

### Step 5.3 — Rehome runtime code if needed

If helpful, move extracted runtime code into:

- `factory_runtime/agents/`
- `factory_runtime/apps/`
- `factory_runtime/tests/`

Expected output:

- runtime packaging can boot without developer/meta folders mounted into the container images

---

## Phase 6 — Unify the environment contract

### Step 6.1 — Standardize environment variables

Adopt the canonical environment contract from `softwareFactoryVscode.md`, especially:

- `TARGET_WORKSPACE_PATH`
- `COMPOSE_PROJECT_NAME`
- `PROJECT_WORKSPACE_ID`
- `FACTORY_INSTANCE_ID`
- `FACTORY_AUDIT_DIR`
- `FACTORY_DATA_DIR`
- `FACTORY_CONFIG_DIR`

### Step 6.2 — Remove deprecated workspace path names

Deprecate and eliminate:

- `PROJECT_WORKSPACE_DIR`
- `WORKSPACE_PATH`

unless temporarily mapped with explicit compatibility logic.

### Step 6.3 — Define the env file layout

Create a documented env model for:

- `.env.example`
- `.factory.env`
- generated runtime env files under `.tmp/softwareFactoryVscode/runtime/<project-id>/`

Expected output:

- compose, scripts, and docs all use the same variable contract

---

## Phase 7 — Carry over the full local developer environment

### Step 7.1 — Preserve VS Code workspace behavior

Port or generate the workspace behavior required by the factory:

- Python interpreter path
- pytest configuration
- terminal temp redirection to `.tmp`
- MCP server wiring
- auto-approve policy settings
- task definitions
- extension recommendations

### Step 7.2 — Preserve extension expectations

Classify extensions as:

- required external
- required workspace-local
- recommended
- optional
- deprecated / not to carry over

### Step 7.3 — Decide what happens to `issueagent`

The current local extension must **not** be copied forward unchanged if it still carries Maestro identity.

Choose one:

- remove it,
- replace it with a neutralized equivalent,
- or keep it only after full renaming and documentation.

### Step 7.4 — Preserve bootstrap ergonomics

Carry over or rewrite the setup helpers that make the workspace operable without manual drift.

Expected output:

 a clean host workspace can acquire the same intended editor behavior through the shipped hidden-tree assets in `.softwareFactoryVscode/` plus documented host-local bootstrap artifacts

---

## Phase 8 — Carry over runtime services and Docker environment

### Step 8.1 — Rehome compose files under `compose/`

Normalize compose files into the destination layout.

Required services include at least:

- memory MCP
- agent bus MCP
- approval gate
- bash gateway MCP
- repo fundamentals MCPs
- devops MCPs
- offline docs MCP
- GitHub ops MCP
- Context7 MCP
- mock LLM gateway if retained

### Step 8.2 — Preserve Docker build inputs

Carry over all required Dockerfiles and supporting assets.

### Step 8.3 — Make Context7 explicit

Treat Context7 as a first-class artefact.

Carry over:

- Context7 Dockerfile
- Context7 compose service
- `PORT_CONTEXT7`
- optional `CONTEXT7_API_KEY`
- VS Code MCP wiring to Context7

### Step 8.4 — Ensure project-scoped runtime isolation

Each consuming host repo must get:

- isolated compose project name
- isolated ports
- isolated state and audit directories
- no shared cross-project collisions

Expected output:

- the packaged runtime stack can build and start independently of the source repo

---

## Phase 9 — Extract the external dependencies and remote GitHub environment

This phase is mandatory. A repo clone is not enough.

### Step 9.1 — Create tracked GitHub artefacts

Add the GitHub artefacts that belong in the repo itself:

- `.github/workflows/ci.yml`
- `.github/workflows/pr-validate.yml` if structured PR validation is retained
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- `.github/CODEOWNERS` if required by merge policy
- label manifest such as `manifests/github-labels.json`

### Step 9.2 — Define remote repository settings

Document and script the remote GitHub settings that cannot be transferred by clone:

- default branch
- branch protection
- required checks
- review requirements
- squash merge policy
- branch auto-delete
- Actions permissions

### Step 9.3 — Define the secrets and variables contract

Document which values are:

- required locally
- optional locally
- required remotely
- optional remotely

Minimum set to classify:

- `GITHUB_TOKEN` / `GH_TOKEN`
- `CONTEXT7_API_KEY`
- `ANTHROPIC_API_KEY`

### Step 9.4 — Add remote-bootstrap tooling

Create or plan scripts such as:

- `scripts/bootstrap_github_repo.py`
- `scripts/verify_github_repo.py`

These should:

- create or target the remote repo
- seed labels
- apply settings
- verify required checks exist
- verify merge guardrails behave as expected

### Step 9.5 — Define host-repo projection modes

Do not assume every consuming host repo wants full GitHub governance.

Support modes such as:

- Local-only mode
- Docs-only mode
- Full-governance mode

Expected output:

- the remote GitHub operating envelope is reproducible and documented, not tribal knowledge

---

## Phase 10 — Add install, bootstrap, and projection flows

### Step 10.1 — Create host installation entrypoint

Provide a package-owned installer such as:

- `scripts/install_factory.py`

### Step 10.2 — Create host bootstrap entrypoint

Provide a host bootstrapper such as:

- `scripts/bootstrap_host.py`

It must:

- validate host repo state
- create `.tmp/softwareFactoryVscode/`
- create `.factory.lock.json`
- create `.factory.env`
- leave tool-owned `.vscode/`, `.github/`, and `.copilot/` inside `.softwareFactoryVscode/`
- prepare runtime env generation

### Step 10.3 — Create projection/isolation entrypoint

Provide a projector such as:

- `scripts/project_projector.py`

It must describe or enforce the hidden-tree isolation model and must not mutate host-project `.vscode/`, `.github/`, or `.copilot/` files by default.

### Step 10.4 — Create runtime lifecycle entrypoints

Provide:

- `scripts/project_runtime_env.py`
- `scripts/project_runtime_up.py`
- `scripts/project_runtime_down.py`
- `scripts/project_runtime_validate.py`

Expected output:

- a blank host repo can install and bootstrap the factory through one documented flow

---

## Phase 11 — Add upgrade and isolation handling

### Step 11.1 — Add the version lock model

Create `.factory.lock.json` with fields for:

- installed version
- schema version
- enabled modules
- projection version
- last upgrade timestamp

### Step 11.2 — Add override locations

Record the hidden-tree isolation rule explicitly:

- `.softwareFactoryVscode/` owns tool configuration
- host repo owns host configuration
- upgrades must preserve that boundary

### Step 11.3 — Add the upgrade command

Create or define:

- `scripts/project_upgrade.py`

It must:

- detect current version
- switch to target version
- preserve host/tool separation
- refresh runtime metadata without projecting tool-owned files into the host repo
- rerun validation
- produce a migration summary

Expected output:

- the package can evolve without requiring consumers to fork or hand-edit package-owned files

---

## Phase 12 — Validate everything in a clean room

### Step 12.1 — Run static checks

Validate:

- required file presence
- runtime/meta boundaries
- neutrality
- variable contract consistency
- documentation presence
- VS Code workspace parity

### Step 12.2 — Run build checks

Validate:

- Python setup
- Docker image builds
- script smoke checks

### Step 12.3 — Run runtime smoke tests

Validate:

- blank host repo install
- bootstrap
- env generation
- stack startup
- health checks
- `/target` visibility
- teardown

### Step 12.4 — Run dual-host isolation tests

Validate two host repos can run simultaneously without collisions.

### Step 12.5 — Run upgrade tests

Validate upgrade from an earlier version with host overrides preserved.

### Step 12.6 — Run remote GitHub proving checks

Validate:

- Actions run on PRs
- required checks appear
- branch protection blocks invalid merges
- PR template / PR validation behaves as documented
- labels and templates exist remotely

Expected output:

- the package is proven, not assumed

---

## Phase 13 — Release the standalone package

### Step 13.1 — Final documentation pass

Ensure the standalone repo contains at minimum:

- `README.md`
- `docs/INSTALL.md`
- `docs/TESTING.md`
- `docs/VSCODE-WORKSPACE.md`
- `docs/UPGRADE.md`
- `docs/MAINTENANCE.md`
- `docs/ARCHITECTURE.md`
- `docs/EXTRACTION-SOURCE-MAP.md`
- `softwareFactoryVscode.md`
- `externalDevendenciesSoftwareFactory.md`
- `SoftwareFactoryVsocdeTestsuite.md`
- `howto-extract-softwareFactory.md`

### Step 13.2 — Protect the remote repo

Apply the documented GitHub settings:

- branch protection
- required checks
- squash merge policy
- workflow safeguards
- label and template seeding

### Step 13.3 — Tag the first release

Publish:

- `v1.0.0`

only after all required validation gates pass.

Expected output:

- `softwareFactoryVscode` is ready to be consumed as a pinned dependency for new host repos

---

## Minimal execution checklist

Use this as the short form when driving the extraction.

- [ ] Freeze source baseline
- [ ] Build include/exclude inventory
- [ ] Create extraction manifest and source map
- [ ] Create `softwareFactoryVscode` repo
- [ ] Create target structure
- [ ] Copy factory assets
- [ ] Neutralize Maestro identity and defaults
- [ ] Remove application coupling
- [ ] Rebuild runtime/meta boundary
- [ ] Unify env contract
- [ ] Preserve VS Code workspace parity
- [ ] Preserve Docker and MCP stack
- [ ] Extract external GitHub dependencies and remote config
- [ ] Add install/bootstrap/projection flows
- [ ] Add upgrade/override model
- [ ] Run clean-room validation
- [ ] Configure remote guardrails
- [ ] Release `v1.0.0`

---

## Common failure points to watch for

1. **Copying repo files but forgetting GitHub-hosted settings**
   - Result: package looks complete locally but merge guardrails do not exist.

2. **Leaving `maestro` naming in defaults, images, or docs**
   - Result: the package is not neutral and leaks source assumptions.

3. **Carrying over runtime code that still depends on meta tooling**
   - Result: runtime images require `.copilot/` or `.github/` to function.

4. **Keeping `/tmp` as host-visible state**
   - Result: hidden, fragile, or unsafe package behavior.

5. **Forgetting VS Code workspace parity**
   - Result: the extracted package technically exists but does not behave like this workspace.

6. **Assuming optional secrets are required for baseline CI**
   - Result: the package becomes hard to adopt and impossible to validate cleanly.

7. **Failing to test blank-host installation**
   - Result: hidden assumptions remain until the first real consumer trips on them.

---

## Definition of done

The extraction is complete only when all of the following are true:

1. `softwareFactoryVscode` exists as a standalone repository.
2. It contains the reusable factory but not Maestro product artefacts.
3. A blank host repo can install it through a documented flow.
4. The full local developer environment can be reproduced.
5. The full runtime stack can be reproduced.
6. The external dependencies and remote GitHub environment can be reproduced.
7. Validation proves install, runtime, isolation, and upgrade behavior.
8. No hidden Maestro-specific coupling remains outside allowed historical references.

---

## Final instruction

Do not treat extraction as a glorified file copy.

Treat it as the migration of a **complete operating environment**:

- source files,
- runtime services,
- editor behavior,
- bootstrap commands,
- validation,
- and remote GitHub guardrails.

If a behavior is necessary for the Software Factory to work, it must be either:

1. copied into the standalone repo,
2. regenerated by package tooling,
3. configured by scripted remote bootstrap,
4. or documented explicitly as an operator step.
