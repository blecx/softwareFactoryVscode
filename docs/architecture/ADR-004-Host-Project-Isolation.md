# ADR 004: Host Project Isolation

## Status

Accepted

## Context

The Software Factory provides an autonomous AI agent capability designed to be installed into target "Host" repositories. Recently, we discovered that the Factory's runtime components (such as `ComplexityScorer`, `CoverageAnalyzer`, `CoderAgent`, and validation profiles) contained hardcoded path references to elements like `apps/api/`, `apps/tui/`, and `tests/`.

This created a severe architectural violation: the Factory's logic was tightly coupled to one specific repository layout (likely the one it was originally developed within). If installed into a standard Host app that uses different folder structures (like `src/`, `frontend/`, `backend/`), the Factory would fail to analyze complexity properly, fail to execute tests, and fail to validate code.

## Decision

We mandate **Strict Isolation** between the Factory Runtime and the Host Project:

1. **No Hardcoded Domains:** The Factory must _not_ hardcode Host-specific file paths, project structures, or business domains anywhere in its runtime logic (`factory_runtime/`).
2. **Dynamic Heuristics:** Tools like `ComplexityScorer` must compute metrics purely structurally (e.g., counting unique top-level directories of changed files) or contextually, without assuming naming conventions.
3. **Agnostic Tooling commands:** Development agents must trigger standard, generalized commands (like `pytest` without path restrictions, or `black .`) and rely on the Host Project's configuration files (e.g., `pyproject.toml`, `tox.ini`, `Makefile`) to define the actual scope and domains of those operations.
4. **Separation of Concerns for Test Execution:** The Factory provides its AI agents with test-running capabilities exclusively via designated MCP Servers (e.g., `devops_test_runner_service`), eliminating redundant or parallel test execution definitions embedded directly in Agent system prompts.

## Consequences

- The Factory will successfully deploy and operate within any arbitrary Host repository without needing code changes.
- Complexity scoring will become domain-agnostic, improving accuracy across diverse repositories.
- Refactoring `test_runner_service` to `devops_test_runner_service` avoids the standard test discovery modules (like `pytest`) from mistakenly executing tool services as unit tests.
