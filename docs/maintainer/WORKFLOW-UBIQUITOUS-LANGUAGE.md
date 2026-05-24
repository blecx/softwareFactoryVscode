# Maintainer Workflow Ubiquitous Language Guide

**Notice:** This is a non-normative derived projection as defined by [ADR-013](../architecture/ADR-013-Architecture-Authority-and-Plan-Separation.md). The definitive definitions of these terms and related policies reside in [ADR-016](../architecture/ADR-016-Workflow-Ubiquitous-Language-and-Ambiguity-Policy.md) and the [workflow language config](../../configs/workflow_language.yml). If this guide ever conflicts with those files, the ADRs and configuration take precedence.

## Ubiquitous Language vs Ambiguous Language

When executing or coordinating work within the repository, we use a strict "ubiquitous language" based on precise terms. Using ambiguous language causes AI automation to attempt to guess meaning, leading to broken boundaries, unauthorized bypasses, or skipped validation.

When an AI agent or maintainer encounters ambiguous workflow requests, the correct action is always to **stop and ask for clarification** or apply the required evidence standards from the workflow language configuration, rather than guessing intent.

## Examples of Ambiguous Requests and Required Actions

The [workflow language config](../../configs/workflow_language.yml) maintains the exact definitions, but here are concrete examples applying those constraints to common conversational shorthand.

### `execute the plan`

- **Ambiguous meaning:** "Do the next thing I want" or ad-hoc conversational planning without a formal issue.
- **Ubiquitous language:** Uses `approved plan` backed by a finite GitHub issue set, umbrella issue, or queue checkpoint.
- **Required Action:** Do not guess the plan. If there is no specific GitHub issue, umbrella issue, or `.tmp/github-issue-queue-state.md` checkpoint, escalate to the operator and ask which formal issue set is approved for execution.

### `continue`

- **Ambiguous meaning:** Processing sibling issues or trying to execute an entire umbrella within a single scope.
- **Ubiquitous language:** Operations are limited to an `issue slice` (a single issue-to-PR execution).
- **Required Action:** Halt execution if boundaries blur with sibling issues. Ensure that the active worktree aligns strictly with a single active issue designated for the current execution lease. Re-anchor to the checkpoint truth as needed.

### `ready`

- **Ambiguous meaning:** "It works locally so we can merge it."
- **Ubiquitous language:** Verification of a `readiness projection` vs final CI validation.
- **Required Action:** Validate against CI and pipeline reality. Ambiguity about whether a build is "ready" means you must assert explicit successful test/validation artifacts or fresh `github truth` before advancing.

### `closeout`

- **Ambiguous meaning:** "Close the current issue" or closing issues manually during an unrelated session.
- **Ubiquitous language:** True `closeout` applies to the final step where an umbrella issue or all children are complete and verifiably closed via GitHub metadata.
- **Required Action:** Do not execute closeout if any child execution state is uncertain, in-progress, or lacking actual GitHub validation indicating closure.

### `bypass`

- **Ambiguous meaning:** An autonomous AI fallback to skip a test, or a suggestion to the user to escape a failure.
- **Ubiquitous language:** Explicit human operator override using `@harness-bypass-resolution`.
- **Required Action:** Never autonomously bypass or suggest bypassing failing validation. Remain within standard CI parity constraints. Bypass is restricted *exclusively* to direct human invocation.

### `production ready`

- **Ambiguous meaning:** A local test passed, or an incomplete release bump.
- **Ubiquitous language:** Indicates a formal `production readiness claim`.
- **Required Action:** Refuse the claim and halt release actions unless all current-release surfaces agree on the version and the release guardrail pass rate matches 100%. Ensure no drift exists.
