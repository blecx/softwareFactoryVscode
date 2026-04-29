# SoftwareFactoryVscode project overview

SoftwareFactoryVscode is the under-development, host-installable software factory behind the `softwareFactoryVscode` repository. It is aimed at enterprise development automation using VS Code and GitHub: teams install a reusable AI workflow harness that brings together prompts, agent workflows, MCP-backed tooling, approval boundaries, and validation gates so delivery stays explicit instead of turning into repo-by-repo improvisation.

This page is the host-owned canonical landing overview for the reader-facing Wiki `Home` projection. It summarizes the project story; accepted ADRs and deeper canonical docs remain authoritative for architecture, runtime, and release boundaries.

## What problem it is trying to solve

Teams adopting AI coding assistants often recreate the same repository layer over and over:

- instructions and prompts,
- agent workflows,
- GitHub issue and PR discipline,
- MCP integrations and runtime helpers,
- approval and safety boundaries,
- and local validation/test expectations.

SoftwareFactoryVscode packages that layer into a reusable VS Code-centered harness so improvements can be made once, reviewed once, and rolled out through a controlled install/update path instead of being re-invented in every host repository.

## Agile and spec-driven workflow

The project is designed around an agile/spec-driven workflow rather than ad-hoc prompting.

Work is supposed to start from explicit GitHub issues, stay bounded as one issue = one PR = one merge, and move through the canonical `resolve-issue` → `pr-merge` path. When a larger effort is approved, the queue is still expected to be finite, GitHub-backed, and explicit rather than vaguely “autonomous.”

That workflow matters because the repository is trying to make AI-assisted delivery reviewable, predictable, and easy to resume after interruptions.

## LLM-assisted development with quality and testing

SoftwareFactoryVscode assumes LLM-assisted development, including quality and testing expectations, is part of the workflow rather than a separate afterthought.

Agents and copilots can help with discovery, implementation, documentation, and PR preparation, but they operate inside guardrails:

- local CI parity instead of “let GitHub discover it later,”
- explicit PR template and issue-template discipline,
- architecture guardrails from accepted ADRs,
- and bounded approval/merge checkpoints.

The goal is not to automate away engineering judgment. The goal is to make AI assistance useful while keeping quality and testing visible enough for humans to trust the result.

## The automation ladder

The intended automation ladder runs from commits to partial projects to entire sprints.

In practice, that means the repository supports a progression like this:

1. commit- and patch-sized assistance;
2. single-issue implementation slices;
3. approved multi-issue or partial-project execution;
4. and, over time, broader sprint-scale delivery where the issue set is still explicit, reviewable, and human-approved.

The top end of that ladder is intentionally still under development. The repository does not claim that every future automation idea is already production-finished today.

## Current status and honest boundary

SoftwareFactoryVscode is explicitly under development.

The current story is a local/internal self-hosted harness for teams that want stronger AI workflow discipline inside VS Code and GitHub. It is not a hosted SaaS platform, not a replacement for a host product architecture, and not a promise that every workflow is fully autonomous already.

That bounded status is part of the value proposition: the project is trying to grow the automation surface without pretending the unfinished parts are already done.

## Where to go next

### Install and get started

- [`INSTALL.md`](INSTALL.md) — full install, update, and readiness authority.
- [`HANDOUT.md`](HANDOUT.md) — guided first-run path for operators.
- [`CHEAT_SHEET.md`](CHEAT_SHEET.md) — terse day-to-day task and command reference.
- [`README.md`](README.md) — documentation router by audience and document type.

### Understand the technical overview and agentic workflow

- [`COPILOT-HARNESS-MODEL.md`](COPILOT-HARNESS-MODEL.md) — why the harness exists as its own repository and how it integrates into host repositories.
- [`WORK-ISSUE-WORKFLOW.md`](WORK-ISSUE-WORKFLOW.md) — the canonical issue → PR → merge workflow and bounded approved-plan execution model.
- [`architecture/INDEX.md`](architecture/INDEX.md) — architecture entrypoint and authority map.
- [`architecture/ADR-INDEX.md`](architecture/ADR-INDEX.md) — accepted ADR catalog for deeper guardrails.

### Understand the project intent and non-goals

- [`WHY-SOFTWARE-FACTORY.md`](WHY-SOFTWARE-FACTORY.md) — shortest public explanation of intent, goals, and non-goals.
- [`../README.md`](../README.md) — repository entrypoint, current release, and top-level orientation.
