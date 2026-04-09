# Harness Namespace Implementation Backlog

This backlog translates the namespace migration mitigation plan into concrete implementation phases.

It is intentionally execution-oriented: each phase lists the goal, likely files to change, dependency order, open questions, Definition of Done (DoD), and review criteria.

This document should be used when preparing actual implementation work. It is designed to reduce guesswork and to prevent AI-assisted coding from inventing requirements that are not yet specified.

See also:

- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- `docs/COPILOT-HARNESS-MODEL.md`

---

## Delivery rules for implementation work

These rules apply to every phase below.

### Rule 1 — Do not guess when ownership is unclear

If a task depends on ownership of a file, namespace, bridge artifact, or runtime state artifact and that ownership is not already specified in the docs, the implementer must stop and ask for clarification rather than guessing.

### Rule 2 — Do not silently widen scope

If a phase reveals adjacent work that is useful but not required for the phase DoD, record it as a follow-up rather than silently expanding the implementation.

### Rule 3 — Keep current-vs-target behavior explicit

If code still supports the hidden-tree model for compatibility, implementation and review must clearly distinguish:

- current compatibility behavior,
- transitional behavior,
- and target namespace-first behavior.

### Rule 4 — Preserve host-owned content by default

If the system cannot prove that a file is factory-managed, generated, or safe to regenerate, it must treat that file as host-owned and non-safe to overwrite.

### Rule 5 — AI must ask open questions instead of hallucinating

For AI-assisted implementation:

- if a requirement is not documented, ask,
- if a migration rule is missing, ask,
- if a target path is ambiguous, ask,
- if a bridge file is not justified, ask,
- if update ownership is unclear, ask.

No implementation phase is considered complete if unresolved architectural questions were answered by assumption instead of explicit decision.

---

## Phase 0 — Backlog gate and artifact inventory

### Phase 0 goal

Create the implementation baseline that all later coding phases depend on.

### Why this phase exists

The migration cannot be implemented safely until the current artifact set and ownership map are explicit enough to drive code changes and tests.

### Phase 0 likely files to change

- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- new inventory artifact under `docs/` or `manifests/`
- possibly `README.md` if new planning references are added

### Phase 0 dependencies

- depends on existing spec docs only
- blocks every later implementation phase

### Phase 0 required tasks

1. Create a concrete artifact inventory of current install/update/runtime outputs.
2. Mark each artifact with its ownership class.
3. Mark each artifact with its future disposition:
   - keep,
   - migrate,
   - replace,
   - optionalize,
   - remove.
4. Record unresolved ownership questions explicitly.

### Phase 0 open questions that must be answered, not guessed

**[RESOLVED]** See `manifests/harness-artifact-inventory.md`

- What should the managed-path record be called and where should it live? (`.copilot/softwareFactoryVscode/lock.json`)
- Which current root-level files are still required in the target model? (Deep nesting is supported)
- Which runtime facts must remain operator-visible? (`.factory.env` moved to `.copilot/softwareFactoryVscode/.factory.env`)

### Phase 0 DoD

- a current-state artifact inventory exists,
- every known artifact is classified and assigned a future disposition,
- unresolved ownership questions are listed explicitly,
- no later phase needs to infer artifact ownership from code behavior alone.

### Phase 0 review criteria

- Is every installer/bootstrap/verifier/runtime artifact represented?
- Are there any ambiguous ownership entries?
- Are future dispositions explicit and non-overlapping?
- Are open questions listed instead of being resolved by assumption?

---

## Phase 1 — Namespace target map and managed subtree design

### Phase 1 goal

Define the exact target structure for `.copilot/softwareFactoryVscode/` and `.github/softwareFactoryVscode/`.

### Phase 1 likely files to change

- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- this backlog document
- possibly new namespace map doc under `docs/` or `manifests/`
- future code references may later affect:
  - `.copilot/**`
  - `.github/**`
  - templates or manifests describing install layout

### Phase 1 dependencies

- depends on Phase 0 artifact inventory
- blocks install, update, and test migration work

### Phase 1 required tasks

1. Define the target subtree layout under `.copilot/softwareFactoryVscode/`.
2. Define the target subtree layout under `.github/softwareFactoryVscode/`.
3. Map each current harness asset to a target location.
4. Identify bridge files that must remain root-visible for discovery.
5. Identify assets that must never be projected into host-owned root namespaces.

### Phase 1 open questions that must be answered, not guessed

**[RESOLVED]** See `manifests/namespace-target-map.md`

- Which GitHub-facing assets truly require root `.github` discovery versus namespaced presence? (Nested under `.github/softwareFactoryVscode/` is supported natively)
- Which Copilot assets can be consumed directly from a namespaced subtree without root projection? (All skills map nested)
- Are any host-root `.copilot` files unavoidable as bridge files? (None needed)

### Phase 1 DoD

- a complete namespace target map exists,
- every current harness asset has a documented target destination,
- `.copilot` is the primary semantic home by design, not only by aspiration,
- `.github` usage is limited to explicit integration needs,
- required bridge files are identified and justified.

### Phase 1 review criteria

- Does every asset have exactly one target destination?
- Is `.github` being used only when justified?
- Are bridge files minimal and explained?
- Are unresolved discovery questions listed explicitly?

---

## Phase 2 — Installer contract redesign

### Phase 2 goal

Redesign the installer contract around managed namespaces instead of the hidden-tree root.

### Phase 2 likely files to change

- `scripts/install_factory.py`
- `scripts/bootstrap_host.py`
- `scripts/factory_workspace.py`
- `scripts/verify_factory_install.py`
- `docs/INSTALL.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`
- `tests/test_factory_install.py`
- possibly templates or future manifest files

### Phase 2 dependencies

- depends on Phase 1 namespace target map
- should not begin until open questions about bridge files are answered

### Phase 2 required tasks

1. Define the future install success contract in code-facing terms.
2. Separate harness projection from optional runtime bootstrap.
3. Introduce the managed-path record contract.
4. Define compatibility mode for existing hidden-tree installs.
5. Update docs to describe compatibility mode vs target mode.

### Phase 2 open questions that must be answered, not guessed

**[RESOLVED]**

- What is the compatibility behavior for already-installed hidden-tree repositories? (**Auto-migrate everything to the new namespaces and remove old artifacts.**)
- Should install support both models during transition, or only migrate forward? (**Force immediate forward migration and drop support for the old path entirely.**)
- Which artifacts become optional instead of mandatory? (**None, we are just transitioning. Generating workspace and env files remains mandatory.**)

### Phase 2 DoD

- installer success is defined by managed namespace projection and ownership clarity,
- harness install and local runtime bootstrap are separated conceptually and operationally,
- managed-path record behavior is defined,
- compatibility mode for existing installs is documented,
- install docs no longer present hidden-tree layout as the preferred end state.

### Phase 2 review criteria

- Does the new install contract match the namespace-first spec?
- Is compatibility behavior explicit?
- Are root-level artifacts either justified, transitional, or deprecated?
- Are unresolved migration decisions documented rather than assumed?

---

## Phase 3 — Update engine and conflict handling

### Phase 3 goal

Make updates safe, deterministic, and ownership-aware.

### Phase 3 likely files to change

- `scripts/install_factory.py`
- `scripts/bootstrap_host.py`
- `scripts/verify_factory_install.py`
- any new managed-path manifest or metadata file
- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/INSTALL.md`
- `tests/test_factory_install.py`
- `tests/test_regression.py`

### Phase 3 dependencies

- depends on Phase 2 install contract redesign
- depends on a stable managed-path record format

### Phase 3 required tasks

1. Implement managed-path record creation and refresh behavior.
2. Define update behavior for:
   - factory-managed files,
   - generated bridge files,
   - host-owned files,
   - conflict cases.
3. Implement non-destructive defaults.
4. Define rollback behavior for partial updates.
5. Add regression coverage for update safety.

### Phase 3 open questions that must be answered, not guessed

- How should modified factory-managed files be handled?
- What conflict UX is expected for operators?
- Which generated files are always safe to regenerate?

### Phase 3 DoD

- update logic is ownership-aware,
- host-owned files are preserved by default,
- conflict states are explicit and testable,
- rollback or recovery expectations are documented,
- update docs match actual behavior.

### Phase 3 review criteria

- Can a reviewer predict update behavior for any file class?
- Are conflict states explicit rather than implied?
- Is host-owned preservation the default?
- Are unanswered conflict questions documented?

---

## Phase 4 — Runtime-state minimization and relocation

### Phase 4 goal

Reduce the architectural weight of transient runtime state.

### Phase 4 likely files to change

- `scripts/bootstrap_host.py`
- `scripts/factory_workspace.py`
- `scripts/factory_stack.py`
- `scripts/verify_factory_install.py`
- `docs/INSTALL.md`
- `docs/HANDOUT.md`
- `tests/test_factory_install.py`
- `tests/test_regression.py`

### Phase 4 dependencies

- depends on Phases 0–3 because artifact ownership and install/update behavior must already be defined

### Phase 4 required tasks

1. Identify root-level runtime artifacts that can move, shrink, or become optional.
2. Preserve only operator-relevant runtime visibility.
3. Remove transient state from the preferred install success definition.
4. Update docs and verification language accordingly.

### Phase 4 open questions that must be answered, not guessed

- Which runtime facts must remain easy for operators to inspect?
- Which runtime artifacts can move to local-only storage without harming operator workflows?
- Should any runtime metadata remain in-repo for portability reasons?

### Phase 4 DoD

- runtime scratch state is clearly separated from harness projection,
- each transient artifact has a documented future disposition,
- unnecessary root-level runtime state is no longer part of the preferred install contract,
- operator-relevant visibility remains available.

### Phase 4 review criteria

- Does any transient runtime artifact still look like product identity without justification?
- Are operator-visible facts preserved where needed?
- Is the line between harness assets and operational state clearer than before?
- Are unresolved operator-visibility questions documented?

---

## Phase 5 — Verification and regression migration

### Phase 5 goal

Move tests and verification from hidden-tree assumptions to namespace-first expectations.

### Phase 5 likely files to change

- `scripts/verify_factory_install.py`
- `tests/test_factory_install.py`
- `tests/test_regression.py`
- possibly `tests/test_multi_tenant.py`
- `docs/INSTALL.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`

### Phase 5 dependencies

- depends on Phases 2–4 because verification should follow the implemented contract

### Phase 5 required tasks

1. Define the future verification contract.
2. Identify and replace hidden-tree-specific test assumptions.
3. Add regression checks for:
   - managed namespaces,
   - managed-path record,
   - bridge-file behavior,
   - host customization preservation,
   - conflict handling.
4. Ensure docs and verifier language align.

### Phase 5 open questions that must be answered, not guessed

- Which compatibility checks must remain for legacy installs?
- What should verifier output say when a repo is still in transitional mode?
- What is the exact success contract for a namespace-first install?

### Phase 5 DoD

- verification rules match the namespace-first architecture,
- regression tests cover the key ownership and migration rules,
- hidden-tree assumptions are either removed or explicitly marked compatibility-only,
- docs and tests describe the same success conditions.

### Phase 5 review criteria

- Does verification enforce the target architecture instead of the old one?
- Are transitional checks clearly labeled?
- Do tests cover ownership safety and update behavior?
- Are unresolved verifier semantics documented?

---

## Phase 6 — Final migration readiness pass

### Phase 6 goal

Confirm the implementation backlog has been completed without hidden assumptions or architecture drift.

### Phase 6 likely files to change

- `docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`
- this backlog document
- possibly `README.md` and `docs/INSTALL.md` for final language cleanup

### Phase 6 dependencies

- depends on completion of Phases 0–5

### Phase 6 required tasks

1. Perform a cross-doc and cross-code consistency review.
2. Confirm all open questions were resolved by explicit decision, not implementation guesswork.
3. Record any remaining follow-up work separately from the completed migration backlog.

### Phase 6 open questions that must be answered, not guessed

- Are any compatibility behaviors still intended to remain permanently?
- Are there any deliberate deviations from the target model that need their own ADR or follow-up?

### Phase 6 DoD

- the docs, code, tests, and verifier all agree on ownership and install/update behavior,
- all earlier phase DoDs are satisfied,
- open questions have either been resolved explicitly or carried forward as named follow-ups,
- no critical behavior depends on undocumented assumptions.

### Phase 6 review criteria

- Can a new maintainer understand the final model without reverse-engineering it?
- Is every major migration rule testable and documented?
- Did any phase complete by assumption instead of explicit decision?
- Are remaining follow-ups clearly separated from the finished migration scope?

---

## Dependency order summary

Implementation should proceed in this order:

1. **Phase 0** — artifact inventory and ownership freeze
2. **Phase 1** — namespace target map
3. **Phase 2** — installer contract redesign
4. **Phase 3** — update engine and conflict handling
5. **Phase 4** — runtime-state minimization
6. **Phase 5** — verification and regression migration
7. **Phase 6** — final migration readiness pass

This order is mandatory unless a later plan explicitly records and justifies a deviation.

## Anti-hallucination review prompt pack

These prompts are intended for implementation review and can be reused per phase.

### Prompt — missing requirements

"Review the current implementation task against `ADR-012`, `docs/HARNESS-INTEGRATION-SPEC.md`, `docs/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`, and `docs/HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md`. Identify any requirement the implementation appears to assume but that is not explicitly documented. The review must treat undocumented assumptions as open questions, not as valid inferred requirements."

### Prompt — ownership safety

"Review the implementation for ownership safety. Verify that files are updated only when they are clearly factory-managed or explicitly generated. Flag any case where host-owned content could be overwritten because the implementation guessed ownership instead of using documented rules."

### Prompt — completion honesty

"Review whether the implementation fully satisfies the phase Definition of Done. Report every partially completed item, every TODO still implied by the code, and every unresolved open question. Do not mark the phase complete if any task depends on assumed behavior rather than documented decisions."

### Prompt — ask instead of guess

"Inspect the implementation and supporting docs for unresolved questions. If the implementation chose a path where the docs did not provide an explicit rule, flag that choice and recommend asking for clarification instead of silently keeping the guessed behavior."
