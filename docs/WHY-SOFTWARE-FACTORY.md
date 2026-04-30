# Why SoftwareFactoryVscode exists

This page is the shortest public explanation of what `softwareFactoryVscode` is for.

It explains intent, goals, and non-goals in plain language. It does **not** redefine architecture or runtime contracts. Per `ADR-013`, accepted ADRs remain the normative source for technical guardrails and terminology.

## The short version

SoftwareFactoryVscode exists because teams that adopt AI coding assistants usually end up rebuilding the same repository-level tooling over and over again:

- prompts and instructions,
- agent workflows,
- MCP integrations,
- approval and safety boundaries,
- runtime helpers, and
- repeatable issue → PR → merge procedures.

When every repository invents that layer from scratch, it becomes inconsistent, hard to update, and easy to weaken by accident.

`softwareFactoryVscode` packages that layer into a reusable, locally operated VS Code harness so improvements can be made once and rolled out through a controlled install/update workflow.

## Who it helps

SoftwareFactoryVscode is primarily for:

- **maintainers** who want one repeatable AI workflow baseline across multiple repositories;
- **operators** who need explicit lifecycle, validation, and recovery surfaces instead of ad-hoc local setup; and
- **developers** who want richer AI assistance inside VS Code without turning every host repository into a custom prompt experiment.

## Goals

The project exists to:

1. **Make repository AI tooling reusable.**
   Improvements to prompts, skills, workflows, and MCP integrations should be maintainable in one place and projected into host repositories safely.
2. **Keep the harness separate from host product code.**
   The supported model is namespace-first installation under `.copilot/softwareFactoryVscode/`, not silent sprawl across product source directories.
3. **Provide a local, inspectable operating model.**
   Runtime lifecycle, readiness, validation, and recovery should use explicit repo-managed surfaces rather than hidden magic.
4. **Standardize guarded delivery workflows.**
   The issue → PR → merge path should be repeatable, reviewable, and backed by local validation before GitHub is asked to discover preventable failures.
5. **Preserve clear authority boundaries.**
   Purpose docs explain the project, while accepted ADRs define architecture guardrails and contracts.

## Current boundary

The truthful `2.6` story is intentionally bounded:

- the project is a **local / internal self-hosted harness**, not a hosted product offering;
- accepted ADRs remain the authority for architecture, terminology, and guardrails;
- runtime and readiness claims must stay aligned with the manager-backed contract and the current operator docs; and
- deeper architectural reasoning still lives in the ADR set and supporting explainer docs.

## Non-goals

SoftwareFactoryVscode is **not** trying to be:

- an external hosted multi-tenant SaaS product;
- a customer-facing cloud platform with billing, internet-hosted tenancy, or SaaS authentication claims;
- a replacement for the host repository's product architecture, source tree, or release story;
- a feature roadmap or backlog document; or
- a competing authority source that overrides accepted ADRs, runtime contracts, or production-readiness boundaries.

It also does **not** imply that every MCP service is globally shared by default or that all future automation ideas are already supported today.

## How this page relates to the deeper docs

Use this page when you want the quick answer to "why does this repository exist?"

Use the deeper docs when you need more:

- [`../README.md`](../README.md) — top-level repository orientation and release surfaces.
- [`README.md`](README.md) — audience-based documentation router.
- [`COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md) — the fuller conceptual explainer behind the harness model.
- [`architecture/INDEX.md`](architecture/INDEX.md) — the entrypoint for accepted ADRs and architecture discovery.
- [`PRODUCTION-READINESS.md`](PRODUCTION-READINESS.md) — the bounded internal production/readiness contract.
