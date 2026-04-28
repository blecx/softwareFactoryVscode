# Copilot Harness Model

This document explains what `softwareFactoryVscode` is supposed to be, why it exists as its own repository, and how it is intended to integrate into host repositories over time.

It is intentionally more human-readable than an ADR. The ADR defines the rules; this document explains the reasoning.

For the shorter public-facing intent/goals/non-goals summary, start with `docs/WHY-SOFTWARE-FACTORY.md`.

See also:

- `docs/WHY-SOFTWARE-FACTORY.md`
- `docs/architecture/ADR-012-Copilot-First-Namespaced-Harness-Integration.md`
- `docs/architecture/ADR-004-Host-Project-Isolation.md`
- `docs/HARNESS-INTEGRATION-SPEC.md`
- `docs/archive/HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`
- `docs/INSTALL.md`

## What `softwareFactoryVscode` is

`softwareFactoryVscode` is a reusable **Copilot enhancement harness** for software projects.

Its job is to provide a centrally maintained set of:

- prompts,
- skills,
- agent workflows,
- MCP integrations,
- runtime helpers,
- and repository workflow conventions

that can be reused across multiple host repositories.

This is why it lives in its own repository: improvements should be made once and then rolled out to many projects through controlled install/update workflows.

## What problem this solves

Most projects eventually accumulate AI-related repository glue:

- Copilot instructions
- prompt files
- workflow agents
- repository automation rules
- runtime helpers
- local MCP integration details

Without structure, these pieces tend to drift, conflict with host tooling, or become hard to update across multiple repositories.

`softwareFactoryVscode` exists to make that layer reusable and maintainable.

## The intended integration model

The important architectural decision is this:

> `softwareFactoryVscode` should integrate into host repositories primarily through existing AI/workflow namespaces, not through host product source directories.

In practice, that means the preferred long-term target is:

- **primary:** `.copilot/softwareFactoryVscode/`
- **secondary:** `.github/softwareFactoryVscode/`

instead of relying on a dedicated root-level `.softwareFactoryVscode/` subtree as the final shape.

## Why `.copilot` comes first

The harness is fundamentally about **Copilot behavior**:

- what the AI sees,
- how it is instructed,
- what workflows it follows,
- how it discovers tools,
- and how it reasons about repository tasks.

That makes `.copilot` the most natural semantic home.

`.github` still matters, but mainly as an integration surface for GitHub-facing workflows, templates, and agent discovery needs.

In short:

- `.copilot` = primary semantic home
- `.github` = secondary integration surface

## Why not just use a root-level `.softwareFactoryVscode/`

The hidden-tree model gave the harness a physically isolated place to live, which was useful early on.

But it also has drawbacks:

- it introduces a custom top-level namespace into every host repository,
- it can feel like a foreign subsystem rather than natural repo tooling,
- it is not the clearest semantic signal for Copilot-facing artifacts,
- and it encourages a bigger separation than the product actually needs.

The project is not only a runtime. It is also a reusable repository AI harness.

That means a namespace strategy inside existing tooling locations is often a better fit than a brand-new root-level directory.

## Ownership model

The following ownership model should guide future work.

| Area                                       | Role                                    | Ownership                                                |
| ------------------------------------------ | --------------------------------------- | -------------------------------------------------------- |
| host product source (`src/`, `app/`, etc.) | product implementation                  | host-owned                                               |
| host `.copilot/`                           | AI/workflow namespace                   | host-owned, factory may integrate via namespaced subtree |
| host `.github/`                            | GitHub/workflow namespace               | host-owned, factory may integrate via namespaced subtree |
| host `.vscode/`                            | editor/workspace tooling                | host-owned                                               |
| host `.gitignore`                          | repository policy                       | host-owned                                               |
| `.copilot/softwareFactoryVscode/`          | preferred factory harness namespace     | factory-managed                                          |
| `.github/softwareFactoryVscode/`           | secondary factory integration namespace | factory-managed                                          |

The key rule is simple:

> host namespaces remain host-owned even when the harness installs managed content into them.

This means install and update workflows must preserve host customizations and avoid silent overwrite behavior.

For the concrete artifact and lifecycle contract that follows from this model, see `docs/HARNESS-INTEGRATION-SPEC.md`.

## Source repository vs installed projection

Another important distinction:

- the **`softwareFactoryVscode` repository** is the canonical source of the harness,
- the **host repository** receives an installed / synchronized projection of that harness.

This lets the harness remain centrally maintained while still living alongside each project.

## Robustness and Copilot context

Using `.copilot` and `.github` is not just about aesthetics. It is also about robustness.

These locations already carry the meaning:

- AI instructions,
- repository workflow,
- tooling,
- automation,

rather than host product source code.

That makes them the best candidates for keeping the harness visible to Copilot without making it look like the host application's implementation tree.

The goal is:

- the harness should be available,
- the host project should stay the default subject of implementation work,
- and humans should be able to understand why the harness files are present.

## Current state vs target state

The active install/update contract has now moved to the namespace-first model:

- `.copilot/softwareFactoryVscode/` is the canonical installed harness path,
- `software-factory.code-workspace` is the host-facing VS Code entrypoint,
- `.copilot/softwareFactoryVscode/.factory.env`, `.copilot/softwareFactoryVscode/lock.json`, and `.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json` are the managed runtime artifacts,
- and legacy root-level artifacts like `.softwareFactoryVscode/`, `.tmp/softwareFactoryVscode/`, `.factory.env`, and `.factory.lock.json` are treated as migration leftovers that must be removed during upgrade.

The older hidden-tree root model remains relevant only as migration history. Repositories that still contain those artifacts are considered non-compliant until cleanup removes them.

The target direction is:

1. prefer namespaced installation under `.copilot/` first,
2. use `.github/` for GitHub-facing integration where needed,
3. keep root-level bridge artifacts minimal,
4. and make install/update workflows explicit, robust, and non-destructive.

## What future humans should remember

If you are reading this later and wondering "why is this spread across `.copilot` and `.github` instead of a single custom folder?", the answer is:

1. this harness is meant to enhance Copilot and repository workflows,
2. `.copilot` is the most semantically appropriate home for that,
3. `.github` is the natural secondary integration surface,
4. and avoiding a custom root-level namespace makes the host repository feel less foreign while improving long-term robustness.

That tradeoff is intentional.
