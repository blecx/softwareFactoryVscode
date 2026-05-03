---
description: "Apply the canonical validation policy for the current task without becoming a second authority source."
name: "Apply Canonical Validation Policy"
argument-hint: "Optional: Validation level, changed files"
agent: "workflow"
model: "GPT-5 (copilot)"
---

## Objective

Evaluate and apply the canonical validation rules against the current context by parsing the single source of truth (`configs/validation_policy.yml`) rather than relying on hardcoded, stale, or hallucinated knowledge.

This is a **non-authoritative** surface. It does not dictate what the rules are; it dynamically reads the repository's living configuration and tells you how to apply it.

## Canonical Policy Source

The single source of truth for validation policy, levels, exclusions, and bounds is:

- `configs/validation_policy.yml`

This file is also projected dynamically by the validation tooling:

- `scripts/local_ci_parity.py --level <focused-local|pr-update|merge|production>`

## Process

1. **Read the Policy**: When invoked, first read `configs/validation_policy.yml` and `configs/validation_policy.yml`.
2. **Match the Context**: Determine which validation level applies to your current state (e.g., `focused-local`, `pr-update`, `merge`).
3. **Execute the Policy**: Run `scripts/local_ci_parity.py --level <level>` ensuring you respect the bounded watchdogs, scope rules, and excluded bundles dictated by the policy.
4. **Use Evidence**: If a check fails, fall back to the evidence-first tactic (`pr-error-resolve-tactic.prompt.md`). Do not guess or widen validation unless the policy says to do so.

Do **not** invent validation rules. If `configs/validation_policy.yml` does not require a bundle, skip it. If it sets a 45-minute timeout, respect it.
