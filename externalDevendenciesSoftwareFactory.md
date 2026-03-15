# externalDevendenciesSoftwareFactory

## Purpose

This document is the authoritative specification for the **external dependencies, GitHub-hosted configuration, and remote repository requirements** that must accompany `softwareFactoryVscode`.

Preserved migration goal line (kept verbatim):

> Always keept the goal, that we like to move the software factory to a new project taking all of its capability, but nothing from maestor.

It exists because a Git repository clone alone is **not sufficient** to reproduce the full Software Factory behavior seen in this workspace.

Some required behavior lives outside ordinary source files, including:

- GitHub Actions workflow execution,
- pull request and issue guardrails,
- branch protection and merge policy,
- repository labels and templates,
- repository secrets and variables,
- GitHub CLI authentication assumptions,
- and remote-repository settings that cannot be transferred by `git clone`.

This specification complements:

- `softwareFactoryVscode.md` — the standalone package extraction and implementation contract
- `SoftwareFactoryVsocdeTestsuite.md` — the validation and release-gate contract

---

## Mandatory outcome

The future standalone repository **`softwareFactoryVscode`** must ship with everything needed to recreate not only the local package contents, but also the **remote GitHub operating envelope** required for the factory workflow.

This external-dependency contract must therefore preserve reusable factory capability while importing no `maestro`-specific remote behavior unless it has been explicitly generalized into a neutral factory requirement.

That means the final deliverable must include:

1. all Git-tracked GitHub assets that belong in the repository,
2. a documented and automatable method to configure the remote GitHub repository,
3. a documented and automatable method to seed labels, templates, and protections,
4. a documented secret/variable contract,
5. a documented local operator authentication contract,
6. validation steps proving that merge guardrails actually work on the remote.

---

## Current-state findings from `maestro`

The current repository already proves that the factory depends on GitHub-side behavior, but the implementation is only partially materialized in tracked files.

### GitHub-side behavior already evidenced in this repo

- `.github/copilot-instructions.md` explicitly refers to:
  - `.github/workflows/ci.yml`
  - `.github/ISSUE_TEMPLATE/feature_request.yml`
- issue creation and issue-selection workflows rely on `gh issue ...` commands
- merge workflows rely on `gh pr ...` commands and required status checks
- PR validation knowledge refers to `.github/pull_request_template.md` and PR-body validation workflows
- multiple scripts assume the existence of a real remote repo via `TARGET_REPO`
- GitHub credentials are expected through `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth login`

### Important gap discovered during audit

The following are **referenced by repo policy and workflow guidance but are not present as tracked files in the current workspace**:

- `.github/workflows/ci.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- `.github/workflows/pr-validate.yml` or equivalent PR-body review gate workflow

Implication:

- `softwareFactoryVscode` must **not** assume these can be copied verbatim from the current repo.
- The standalone package must instead define them explicitly and create them as first-class artefacts.

This is the central reason this companion specification is necessary.

---

## Dependency model

All external dependencies for `softwareFactoryVscode` must be classified into four buckets.

### Bucket A — Git-tracked GitHub artefacts

These must live inside the repository and travel with normal clone/fork operations.

Examples:

- `.github/workflows/*.yml`
- `.github/ISSUE_TEMPLATE/*.yml`
- `.github/pull_request_template.md`
- `.github/CODEOWNERS` if review protection depends on it
- label manifests or repo-settings manifests under `manifests/` or `scripts/`

### Bucket B — Remote GitHub repository settings

These live on GitHub and do **not** transfer by git clone.

Examples:

- default branch selection
- branch protection rules
- required status checks
- merge method settings
- branch deletion behavior
- Actions permissions
- environment protection rules

### Bucket C — Credentials, secrets, and variables

These are external values and must never be committed as live secrets.

Examples:

- `GITHUB_TOKEN` / `GH_TOKEN`
- `CONTEXT7_API_KEY`
- provider keys such as `ANTHROPIC_API_KEY` (if used)
- repository variables such as default target repo slugs or workflow flags, if adopted

### Bucket D — Local operator prerequisites

These are required on the machine of the operator or maintainer.

Examples:

- authenticated GitHub CLI
- Docker
- Python
- Node.js where required
- VS Code extensions defined by `softwareFactoryVscode.md`

---

## Mandatory GitHub repository artefacts

The standalone `softwareFactoryVscode` repository must contain the following tracked GitHub artefacts.

## Workflows

### 1. `.github/workflows/ci.yml`

This is mandatory.

It must validate the repository on at least:

- `push`
- `pull_request`

It must cover at minimum:

- Python environment setup
- static validation
- runtime/meta boundary checks
- neutrality checks
- install/bootstrap validation
- test-suite execution aligned with `SoftwareFactoryVsocdeTestsuite.md`

It must be the baseline required check for merging.

### 2. `.github/workflows/pr-validate.yml`

This is strongly recommended and should be treated as mandatory if the package keeps a structured PR-body workflow.

It should validate at minimum:

- presence of required PR sections
- evidence formatting expectations
- cross-repo impact section presence
- any required issue-linking convention

Because current repo knowledge explicitly depends on PR-body validation behavior, the standalone package should formalize it rather than leaving it tribal.

### 3. `.github/workflows/release.yml`

Recommended for tagged releases.

It should:

- validate the release tag,
- build any release bundle if the package supports one,
- attach release notes or generated artefacts,
- prove versioned install/upgrade behavior remains documented.

### 4. `.github/workflows/remote-bootstrap-verify.yml`

Recommended if repository settings are applied by script.

It should confirm that:

- required labels exist,
- required templates exist,
- required settings manifest is still in sync with docs,
- and required status check names match current workflow job names.

---

## Templates and policy files

### 1. `.github/ISSUE_TEMPLATE/feature_request.yml`

This is mandatory if issue-creation automation is part of the package.

Its required sections must match the documented workflow expectations already visible in this repo:

- Goal / Problem Statement
- Scope
- Acceptance Criteria
- API Contract when applicable
- Technical Approach
- Testing Requirements
- Documentation Updates

### 2. `.github/ISSUE_TEMPLATE/bug_report.yml`

Recommended.

If the standalone package is intended for broad reuse, a bug template should exist for:

- observed behavior,
- expected behavior,
- reproduction steps,
- environment,
- validation evidence.

### 3. `.github/pull_request_template.md`

Mandatory if PR validation or merge policy depends on structured evidence.

At minimum it must contain sections for:

- summary
- linked issue
- scope and affected areas
- validation / evidence
- cross-repo impact
- follow-ups

The package should keep these headings stable, because workflow automation may validate them literally.

### 4. `.github/CODEOWNERS`

Recommended.

Treat as mandatory if the intended merge model requires code-owner approval for:

- workflow changes,
- security-sensitive scripts,
- Docker runtime definitions,
- MCP infrastructure,
- or policy files.

### 5. Label manifest

The package must include a machine-readable label source of truth, for example:

- `manifests/github-labels.json`, or
- `.github/labels.yml`

This is mandatory if any automation depends on labels.

Based on current repo evidence, the label baseline should support at least:

- status labels such as `status:ready` and `status:blocked`
- track labels such as `track:step2-backend` or their neutralized equivalents
- size labels such as `size:S`, `size:M`, `size:L`
- domain labels if the packaged workflow still uses domain routing

All Maestro-specific labels must be neutralized before publication.

---

## Mandatory remote GitHub repository settings

These settings cannot be versioned purely by git, so `softwareFactoryVscode` must document and preferably automate them.

## Repository baseline settings

The remote repository should use:

- default branch: `main`
- issues: enabled
- pull requests: enabled
- discussions: optional
- wiki: optional, disabled by default unless used intentionally
- projects: optional, disabled by default unless workflow requires them

## Merge policy

The default merge policy should be:

- **squash merge enabled**
- merge commits optional or disabled
- rebase merge optional or disabled
- auto-delete head branches enabled after merge

Rationale:

- current repo guidance already prefers squash merges and branch cleanup

## Branch protection for `main`

The `main` branch must be protected with at least:

- pull request required before merge
- direct push disallowed for non-admin users
- force pushes disabled
- branch deletion disabled
- required status checks enforced
- conversations resolved before merge

Recommended additional settings:

- at least one approving review
- dismiss stale approvals on new commits
- require branch to be up to date before merge
- require code-owner review when `CODEOWNERS` is present

## Required status checks

At minimum, merging must require the checks produced by:

- `ci.yml`
- `pr-validate.yml` when that workflow is enabled

The exact required check names must be documented in the repo and verified by automation.

Important rule:

- if workflow job names change, the repository settings bootstrap must update required-check names as well

## Workflow-change guardrails

The standalone package should explicitly protect workflow and policy files.

At minimum one of the following must be implemented:

1. CODEOWNERS + required code-owner review for:
   - `.github/workflows/**`
   - `.github/**`
   - `compose/**`
   - `docker/**`
   - `scripts/**`
2. a PR validation workflow that fails unless workflow changes carry explicit approval metadata
3. both of the above, which is preferred

This aligns with the existing merge policy culture in the repo, where workflow-file merges are already treated as special.

---

## Required secrets and variables contract

The standalone package must define which values are needed locally, which are needed remotely, and which are optional.

## Local operator credentials

The package must document that local issue/PR automation requires one of:

- `gh auth login`, or
- `GH_TOKEN`, or
- `GITHUB_TOKEN`

This is mandatory because current scripts and services rely on GitHub CLI access and token discovery.

## Repository secrets

The remote repo should avoid requiring paid/provider secrets for baseline CI whenever possible.

Mandatory principle:

- **baseline CI for `softwareFactoryVscode` must pass without requiring live proprietary model credentials**

Therefore:

- `ANTHROPIC_API_KEY` must be optional for baseline CI
- `CONTEXT7_API_KEY` must be optional unless a specific workflow mode requires it

If any extended workflow requires those values, document them as **optional extended-mode secrets** rather than core bootstrap requirements.

## Suggested secret classification

### Core local secrets

- `GITHUB_TOKEN` or `GH_TOKEN`

### Optional local/remote secrets

- `CONTEXT7_API_KEY`
- `ANTHROPIC_API_KEY`

### Forbidden practice

- do not commit live secrets to the repo
- do not require maintainers to hand-edit undocumented settings in GitHub UI without recording them in the package docs or bootstrap scripts

## Repository variables

If the package introduces repo variables, they must be documented and ideally set by script.

Possible examples:

- `FACTORY_DEFAULT_BRANCH=main`
- `FACTORY_LABEL_SCHEMA_VERSION=1`
- `FACTORY_PR_TEMPLATE_VERSION=1`

If such variables are not required, do not invent them gratuitously.

---

## Required local tooling dependencies for remote operations

To fully transfer and operate the factory against a remote GitHub repository, the package must document these operator prerequisites.

### Mandatory

- `git`
- `gh` (GitHub CLI)
- authenticated GitHub account with sufficient repository permissions
- Python runtime required by package scripts
- Docker runtime required by the MCP stack

### Conditionally mandatory

- Node.js if the packaged workflow or workspace-local extensions require build steps
- VS Code with the extension matrix defined in `softwareFactoryVscode.md`

### Permission model

The maintainer applying remote repository settings must have sufficient permissions to:

- create the repository
- push branches and tags
- configure branch protection
- configure required status checks
- create labels
- manage repository secrets/variables
- enable Actions

---

## Remote bootstrap contract

The standalone package must include a documented and preferably scripted remote-bootstrap flow.

The preferred implementation is a script such as:

- `scripts/bootstrap_github_repo.py`

or an equivalent shell/Python command set.

## Required bootstrap steps

### Step 1 — Create or select the remote repo

- create GitHub repository `softwareFactoryVscode`
- set default branch to `main`
- push baseline repository contents

### Step 2 — Apply Git-tracked GitHub assets

Ensure the repo contains:

- workflow files
- issue templates
- pull request template
- CODEOWNERS if used
- label/settings manifests

### Step 3 — Seed labels

Create all labels declared by the package manifest.

This step must be idempotent.

### Step 4 — Apply branch protection and merge rules

Configure:

- required PRs
- required checks
- review requirements
- squash merge policy
- branch deletion behavior

### Step 5 — Configure repository secrets and variables

This step must:

- declare which values are required
- skip optional values safely when absent
- never print live secret values in logs

### Step 6 — Verify Actions and merge guardrails

The package must provide a verification procedure that proves:

- workflows execute
- required checks appear on PRs
- PR template and/or PR validation behaves as documented
- merges are blocked when required checks fail

### Step 7 — Run a proving PR

The package should require a test PR that validates the end-to-end GitHub guardrails, including:

- CI execution
- PR template enforcement
- branch protection enforcement
- required status check gating

---

## Transfer requirements for consuming host repositories

If `softwareFactoryVscode` is used as a pinned dependency inside another host repository, the host repository may also need remote GitHub configuration if the full issue/PR workflow is projected into that host.

The package must therefore distinguish between:

### Factory-repo remote requirements

Requirements needed for maintaining the `softwareFactoryVscode` repository itself.

### Host-repo remote requirements

Requirements needed only when the host repository adopts the package’s GitHub workflows, templates, or issue/PR automation.

Default architectural rule:

- host repositories do **not** receive tool-owned `.github/`, `.copilot/`, or `.vscode/` material from `softwareFactoryVscode` by default
- the tool remains self-contained under `.softwareFactoryVscode/`
- any host-repo governance projection must be an explicit, separately documented opt-in mode

The package must not silently assume that every host repo wants the full GitHub governance surface.

Instead, it must define projection modes such as:

- **Local-only mode** — no GitHub workflow projection into host
- **Docs-only mode** — host receives guidance, not active GitHub automation
- **Full-governance mode** — host receives templates, workflows, labels, and bootstrap instructions for remote setup

Preferred default mode:

- **Local-only mode** with the tool living under `.softwareFactoryVscode/` as a hidden working tree

---

## Required deliverables in `softwareFactoryVscode`

The standalone package must include at minimum:

- `.github/workflows/ci.yml`
- `.github/ISSUE_TEMPLATE/feature_request.yml`
- `.github/pull_request_template.md`
- a label manifest
- documentation for remote GitHub setup
- a scripted or precisely documented remote-bootstrap procedure
- a documented secrets/variables contract
- validation proving that remote merge guardrails work

Recommended additional deliverables:

- `.github/workflows/pr-validate.yml`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/CODEOWNERS`
- `.github/settings` manifest or equivalent repo-settings script inputs
- `scripts/bootstrap_github_repo.py`
- `scripts/verify_github_repo.py`

---

## Explicit non-goals

This specification does **not** require:

- storing live secrets in source control
- mandating proprietary providers for baseline CI
- forcing every consuming host repository to adopt all GitHub governance features
- copying Maestro-specific labels, branch names, repo IDs, or issue queues unchanged

---

## Acceptance criteria

This specification is successfully implemented only when all of the following are true:

1. `softwareFactoryVscode` ships the required GitHub workflow and template files as tracked artefacts.
2. The remote GitHub repository can be configured reproducibly from package docs and/or scripts.
3. Required status checks are active on the protected branch.
4. Merge policy and branch protection reflect the documented guardrails.
5. Labels and templates required by automation exist remotely.
6. Local issue/PR tooling works with documented GitHub authentication.
7. Baseline CI does not require paid or proprietary secrets.
8. A proving PR demonstrates that CI and merge guardrails actually work.
9. Host-repo projection modes clearly distinguish local-only from full remote-governance setup.

---

## Final instruction to the next step

The next implementation step must treat GitHub remote configuration as a **first-class part of the software factory**, not as an afterthought.

If a behavior depends on GitHub but is not transferred by a normal clone, it must be handled by one of these mechanisms:

1. a tracked file in the standalone repo,
2. a bootstrap script,
3. a repo-settings manifest,
4. or explicit installation documentation.

No required GitHub-side behavior may remain implicit.
