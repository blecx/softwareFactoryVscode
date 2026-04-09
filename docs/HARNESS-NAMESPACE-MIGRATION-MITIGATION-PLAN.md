# Harness Namespace Migration Mitigation Plan

This plan turns the namespace-first direction from `ADR-012` and `docs/HARNESS-INTEGRATION-SPEC.md` into a staged mitigation sequence.

It is intentionally **findings-driven** rather than implementation-first. The goal is to reduce architectural drift, preserve updateability, and move from the current hidden-tree installer toward a `.copilot`-first and `.github`-second integration model without breaking existing host repositories.

Each step includes:

- the goal,
- the findings being addressed,
- the required changes,
- a strict **Definition of Done (DoD)**,
- a concrete **verification method**,
- and **review prompts** that can be used by humans or pasted into Copilot Chat for structured review.

See also:

- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/COPILOT-HARNESS-MODEL.md`
- `docs/INSTALL.md`

---

## Success criteria

This mitigation is complete when all of the following are true:

1. the project has a clear, testable ownership model for harness artifacts,
2. install and update workflows target namespaced `.copilot` / `.github` integration rather than a root-level hidden-tree as the preferred end state,
3. host-owned files are preserved by default,
4. transient runtime state is minimized and no longer overdefines installation success,
5. docs, tests, and installer behavior use the same vocabulary for ownership and managed paths,
6. existing installs have a compatibility-aware migration path,
7. and reviewers can verify the migration with explicit review prompts and exit criteria.

---

## Step 1 — Freeze the ownership vocabulary and artifact inventory

### Step 1 goal

Make the current and target artifact model explicit enough that later code changes cannot silently redefine ownership.

### Step 1 findings addressed

- previous docs explained the architecture direction but did not yet force implementation work to use a single ownership vocabulary,
- install/update logic currently mixes canonical harness content, generated artifacts, and runtime state,
- future changes could drift if no authoritative artifact inventory exists.

### Step 1 changes

1. Inventory current harness-related artifacts produced by install, bootstrap, runtime, and update flows.
2. Classify each artifact as one of:
   - canonical harness asset,
   - managed installed namespace artifact,
   - host-owned integration surface,
   - local-only / ephemeral runtime state,
   - root-level bridge artifact.
3. Record the inventory in a form usable by later implementation and test work.
4. Align naming across docs and code comments with the vocabulary from `docs/HARNESS-INTEGRATION-SPEC.md`.

### Step 1 Definition of Done

- every artifact produced or expected by current install/update flows has an ownership classification,
- the artifact inventory distinguishes current implementation from target architecture,
- there is no ambiguity about whether a file is host-owned, factory-managed, generated, or ephemeral,
- later migration tasks can point to the inventory instead of inferring ownership from installer side effects.

### Step 1 verification

- review installer/bootstrap/verifier/runtime docs against the artifact inventory,
- confirm that the inventory covers install, update, verification, runtime, and cleanup paths,
- confirm that the inventory uses the same terminology as `ADR-012` and `docs/HARNESS-INTEGRATION-SPEC.md`.

### Step 1 review prompts

#### Review prompt — completeness

"Review the artifact inventory for `softwareFactoryVscode`. Verify that every artifact created, required, or updated by install, bootstrap, verification, runtime, and cleanup flows is classified into exactly one ownership class. Report any missing artifacts, double-classified artifacts, or ambiguous ownership."

#### Review prompt — consistency

"Compare the artifact inventory against `ADR-012` and `docs/HARNESS-INTEGRATION-SPEC.md`. Report any terminology drift, ownership mismatch, or artifact that contradicts the namespace-first integration model."

---

## Step 2 — Define the managed namespace projection model

### Step 2 goal

Specify exactly what should live under `.copilot/softwareFactoryVscode/` and `.github/softwareFactoryVscode/`, and what should not.

### Step 2 findings addressed

- the project now prefers namespaced integration, but the concrete distribution of assets is not yet formally mapped,
- without a projection model, migration work could recreate hidden-tree sprawl inside `.copilot` or `.github`,
- `.copilot` is the primary semantic home, but `.github` still needs a bounded secondary role.

### Step 2 changes

1. Define the target subtree layout for `.copilot/softwareFactoryVscode/`.
2. Define the target subtree layout for `.github/softwareFactoryVscode/`.
3. For each current harness asset, decide whether it belongs in:
   - `.copilot/softwareFactoryVscode/`,
   - `.github/softwareFactoryVscode/`,
   - a minimal root-level bridge artifact,
   - or local-only runtime state.
4. Document which assets must remain discoverable through native root locations and why.
5. Document assets that should never be projected into host-owned root namespaces.

### Step 2 Definition of Done

- a target namespace map exists for primary and secondary managed subtrees,
- every projected artifact has a documented reason for its chosen destination,
- `.copilot` is the clear primary home for Copilot-facing behavior,
- `.github` is clearly limited to GitHub-facing integration needs,
- root-level bridge files are minimized and explicitly justified.

### Step 2 verification

- compare the target namespace map against the current repository structure,
- confirm no asset remains unassigned,
- confirm that all proposed root-level bridge artifacts have a tool-discovery or ergonomics justification.

### Step 2 review prompts

#### Review prompt — namespace fit

"Review the proposed mapping of harness assets into `.copilot/softwareFactoryVscode/` and `.github/softwareFactoryVscode/`. Identify any artifact that is assigned to the wrong namespace, any artifact that should remain local-only, or any root-level bridge file that is not clearly justified."

#### Review prompt — semantic clarity

"Evaluate whether the target namespace map makes `.copilot` the primary semantic home and `.github` the secondary integration surface. Call out anything that still treats `.github` as the canonical home of Copilot behavior."

---

## Step 3 — Replace the hidden-tree installer contract with a managed namespace install contract

### Step 3 goal

Redefine installation success around managed namespaces and ownership clarity rather than around the hidden-tree `.softwareFactoryVscode/` layout.

### Step 3 findings addressed

- the current installer treats hidden-tree artifacts and related root-level files as the install contract,
- this no longer matches the preferred end-state architecture,
- install success is currently too dependent on runtime-oriented artifacts rather than the harness integration contract itself.

### Step 3 changes

1. Define the future install contract in terms of:
   - managed namespaces,
   - managed-path record,
   - minimal bridge files,
   - and explicit ownership metadata.
2. Separate install-time harness projection from optional runtime bootstrap.
3. Identify which existing root-level artifacts should become:
   - eliminated,
   - optional,
   - migrated,
   - or replaced by namespaced equivalents.
4. Define compatibility behavior for repositories still using the hidden-tree layout.
5. Update docs so install instructions distinguish compatibility mode from target mode.

### Step 3 Definition of Done

- the future install contract no longer depends on hidden-tree layout as the preferred steady-state model,
- harness installation and local runtime bootstrap are defined as separate concerns,
- all root-level install artifacts have a future disposition (keep, replace, migrate, or remove),
- compatibility behavior for existing installs is documented.

### Step 3 verification

- compare the future install contract against current installer expectations,
- confirm that every root-level artifact from the current model has a documented future disposition,
- confirm that install docs and architecture docs no longer conflict about what “successful install” means in the target model.

### Step 3 review prompts

#### Review prompt — install contract

"Review the proposed namespace-first install contract. Verify that installation success is defined by managed harness projection and ownership clarity, not by hidden-tree-specific runtime artifacts. List any remaining places where the old hidden-tree model is still treated as the preferred install contract."

#### Review prompt — compatibility risk

"Review the install contract for compatibility with existing hidden-tree installs. Identify any migration risk, missing fallback behavior, or place where the transition plan would strand current users."

---

## Step 4 — Define a safe update and conflict-handling model

### Step 4 goal

Make updates deterministic, non-destructive, and ownership-aware.

### Step 4 findings addressed

- central maintainability is one of the reasons this project exists,
- updateability is impossible to preserve without explicit ownership and conflict rules,
- host-owned `.copilot`, `.github`, `.vscode`, and `.gitignore` files must not be overwritten just because the harness now integrates through those namespaces.

### Step 4 changes

1. Define the managed-path record format and its minimum required fields.
2. Define how updates distinguish:
   - factory-managed files,
   - generated bridge files,
   - host-owned files,
   - and conflict states.
3. Define the conflict policy for modified managed files in host repositories.
4. Define migration behavior when a managed file moves from one approved namespace to another.
5. Define rollback / recovery expectations when an update only partially applies.

### Step 4 Definition of Done

- update behavior is defined for all ownership classes,
- the project has a documented managed-path record contract,
- conflict states are explicit rather than inferred,
- update workflows default to preserving host-owned files,
- migration and rollback expectations are documented.

### Step 4 verification

- review sample update scenarios against the policy,
- confirm that a reviewer can determine update behavior for any file without guessing,
- confirm that docs and future test cases can map directly to the managed-path record model.

### Step 4 review prompts

#### Review prompt — ownership safety

"Review the update and conflict-handling model. For each ownership class, confirm whether update behavior is deterministic and safe. Report any case where a host-owned file could still be overwritten implicitly or where a factory-managed file cannot be updated reliably."

#### Review prompt — managed-path record

"Review the proposed managed-path record. Verify that it contains enough information to support safe updates, bridge-file regeneration, migration between namespaces, and conflict detection. Report any missing fields or ambiguous semantics."

---

## Step 5 — Minimize and relocate transient runtime state

### Step 5 goal

Prevent runtime scratch state from dominating the product identity or the installation contract.

### Step 5 findings addressed

- the current implementation still elevates some runtime metadata and scratch state into repo-root contract status,
- the long-term architecture treats runtime state as operational and preferably local-only,
- failing to slim this down would undermine the namespace-first migration even if the harness assets move correctly.

### Step 5 changes

1. Identify which current runtime artifacts are truly required for operator workflows.
2. Identify which runtime artifacts can move out of the host repo root.
3. Identify which artifacts can become optional, generated-on-demand, or local-only.
4. Define which runtime facts must remain visible to operators and where they should live.
5. Update docs so runtime state is described as operational support data, not the core harness identity.

### Step 5 Definition of Done

- runtime scratch state is clearly separated from harness projection,
- each current runtime artifact has a future disposition,
- no unnecessary transient artifact remains part of the preferred install success definition,
- operator-visible runtime information is still preserved where needed.

### Step 5 verification

- compare current root-level runtime artifacts against the future disposition table,
- confirm that remaining operator-visible metadata has a documented reason to exist,
- confirm that docs no longer imply that transient runtime state defines the harness architecture.

### Step 5 review prompts

#### Review prompt — runtime minimization

"Review the future disposition of runtime artifacts. Identify any transient state that is still being treated as a first-class install artifact without strong justification, and any operator-critical runtime metadata that lacks a clear retained location."

#### Review prompt — product clarity

"Review whether the proposed runtime-state changes preserve the distinction between the reusable harness and machine-local operational state. Call out any design choice that would continue to make runtime scratch artifacts feel like part of the product identity."

---

## Step 6 — Align verification, tests, and docs with the namespace-first model

### Step 6 goal

Make the migration durable by ensuring review, tests, and documentation all enforce the same target model.

### Step 6 findings addressed

- current verification and tests still encode the hidden-tree installer contract,
- docs and code can drift unless the verification layer is updated with the new ownership model,
- architecture is only durable when regression tests and review prompts reinforce it.

### Step 6 changes

1. Define the future verification contract for namespace-first installs.
2. Identify which current tests encode hidden-tree assumptions and how they should evolve.
3. Add regression expectations for:
   - managed namespaces,
   - managed-path record behavior,
   - conflict handling,
   - bridge-file policy,
   - and host customization preservation.
4. Update docs to keep “current implementation” and “target architecture” language accurate during migration.
5. Add final review prompts covering both architecture and operator experience.

### Step 6 Definition of Done

- the future verification contract is defined in namespace-first terms,
- test migration requirements are documented,
- docs, verification rules, and ownership vocabulary are aligned,
- final review prompts exist for architecture, install, update, and operator ergonomics.

### Step 6 verification

- compare the future verification contract against `docs/HARNESS-INTEGRATION-SPEC.md`,
- confirm that every major migration risk has a matching review or regression expectation,
- confirm that the docs accurately describe transitional vs target behavior.

### Step 6 review prompts

#### Review prompt — verification alignment

"Review the future verification and regression strategy for the namespace-first migration. Confirm that install, update, ownership, bridge-file behavior, and host customization preservation all have explicit verification coverage. Report any unverified architectural rule."

#### Review prompt — doc consistency

"Review the documentation set for `softwareFactoryVscode` after the namespace migration plan. Confirm that current implementation, target architecture, and transitional compatibility are described consistently. Report any contradiction, outdated hidden-tree assumption, or missing migration guidance."

---

## Final confidence pass

Before declaring the mitigation plan complete and ready for implementation, perform a final structured review.

### Final Definition of Done

- the architecture direction, explainer, spec, and mitigation plan all agree,
- the migration plan covers artifact inventory, namespace projection, install, update, runtime minimization, and verification,
- every step has explicit exit criteria and review prompts,
- the plan is detailed enough to drive implementation without guessing ownership rules,
- the plan is still readable by future maintainers without drowning them in low-level implementation detail.

### Final verification

- read `ADR-012`, `docs/COPILOT-HARNESS-MODEL.md`, `docs/HARNESS-INTEGRATION-SPEC.md`, and this mitigation plan together,
- confirm that each document has a distinct role,
- confirm that no major migration question remains undocumented.

### Final review prompts

#### Final review prompt — architecture readiness

"Review the namespace migration documentation set for `softwareFactoryVscode` as if you were preparing the first implementation PR. Confirm whether the architecture direction, artifact specification, and mitigation plan are implementation-ready. Report any unresolved design question, missing ownership rule, or migration ambiguity that would still force guesswork during coding."

#### Final review prompt — operator readiness

"Review the migration plan from the perspective of a repository operator who already has hidden-tree installs in the wild. Confirm whether the plan explains compatibility, safety, and update behavior clearly enough to proceed without surprising existing users. Report any operator-facing ambiguity or migration risk that still needs documentation before implementation starts."

---

## Recommended execution order

To reduce risk and keep the migration reviewable, implement the work in this order:

1. artifact inventory and ownership freeze,
2. namespace projection model,
3. install contract replacement,
4. update and conflict-handling model,
5. runtime-state minimization,
6. verification/test/doc alignment,
7. final migration confidence pass.

This order preserves the most important invariant first: clear ownership. Once ownership is explicit, install/update logic and verification can evolve without guesswork.
