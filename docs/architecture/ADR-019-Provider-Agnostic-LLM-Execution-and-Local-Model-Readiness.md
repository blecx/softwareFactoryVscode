# ADR-019: Provider-Agnostic LLM Execution and Local-Model Readiness

## Status
Accepted

## Context
With the introduction of the small-model execution production line and compact context constraints (ADR-018), standard GitHub models (e.g., `gpt-4o-mini`, `gpt-4o`) serve as the default provider for LLM intelligence via the agent-bus and registry. However, developers operating with strict privacy boundaries, offline environments, or custom hardware want to substitute execution slices with local-model providers without breaking the orchestration/factory pipeline. The workflow harness and execution surface previously hardcoded GitHub models for operations.

## Decision

1. **Provider-Agnostic Execution Profiles:** The routing and model-fit policies defined in ADR-018 shall become provider-agnostic. The execution harness must map requested tiers (`tier: mini`, `tier: full`) dynamically via a registry instead of directly emitting proprietary model strings.

2. **GitHub as Current Production Baseline:** All verification, local CI-parity prechecks, and baseline integration test suites remain baselined and asserted against the GitHub LLM APIs as the primary authoritative provider. This prevents breaking standard operations during provider transitions.

3. **Local-Provider Eligibility Gates:** Any integrated local-model provider must pass local regressions and demonstrate compatibility with existing factory execution limits (time watchdogs, format consistency, token budgeting) to be registered as an eligible backend. It will operate under the same validation rules.

## Consequences
- **Positive:** Enables safe integration of local/open-weight models offline without compromising pipeline integrity.
- **Positive:** Allows switching backends uniformly via a standard registry instead of rewriting discrete planner/coder agents.
- **Negative:** Increased complexity in maintaining the abstraction layer for prompts across disparate providers.
