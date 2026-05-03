---
description: "Resolve PR-creation, local-precheck, and CI failures using a fast evidence-first tactic: parse current failure output, start with the cheapest failing gate, fix the root cause, and widen validation only after the fast gate passes."
name: "PR Error Resolve Tactic"
argument-hint: "Optional: PR number, issue number, failing check, failing command, failing file/test, or pasted terminal output"
agent: "workflow"
model: "GPT-5 (copilot)"
---

## Objective

Resolve PR-creation, local-precheck, and CI failures quickly **without** broad scanning, stale-state guessing, hallucinated state, or trial-and-error churn.

This prompt now documents the repository's **canonical default PR-error repair behavior**. The guardrails and workflow skills enforce the same method even when this prompt is not explicitly invoked; using the prompt simply foregrounds that default tactic in the conversation. It does **not** override immutable repository guardrails such as:

- ADR and architecture compliance
- execution-surface discipline
- GitHub-truth requirements
- one issue = one PR = one merge
- `.tmp/`, never `/tmp`
- evidence-first repair requirements

Treat [repo guardrails](../copilot-instructions.md) and the [canonical issue workflow](../../docs/WORK-ISSUE-WORKFLOW.md) as binding constraints. This prompt only narrows **how** error resolution should proceed so the agent finds the root cause faster.

## When to Use

- A PR body/template check, local validation, or GitHub CI check has failed and the user wants the fastest compliant repair path.
- Terminal output or CI output already names a failing file, test, assertion, method, command, or check.
- The user explicitly says things like:
  - `parse the output`
  - `stop scanning everything`
  - `find the root cause`
  - `fix it fast`
  - `don't do trial and error`
  - `formatter first`

## When Not to Use

- The task is broad feature development with no concrete failure yet.
- The user wants a full exploratory repo audit.
- The task is architecture design rather than failure resolution.

## Controlling Tactic

### 1. Re-anchor only enough to fix the failure

Start with the **minimum** state needed to act safely:

- active worktree / branch
- changed files
- active issue / PR if relevant
- exact failing command or check

Do **not** begin with a repo-wide scan, broad semantic search, or full parity run unless the current failure evidence is ambiguous.

### 2. Parse the current failure output before rerunning anything

If terminal output, CI logs, or prior command output already identifies the failure:

- quote the **exact failing command or check**
- quote the **relevant error text**
- name the **suspected root cause**
- identify the exact file / test / assertion / method / line when possible

If the output already points to a specific file or method, read **that exact implementation** before running wider validation.

### 3. Reproduce the cheapest failing gate first

Prefer the smallest deterministic reproduction that can fail quickly:

1. file-level formatter check on touched Python files
2. the single failing test or failing test file
3. the touched-test bundle
4. focused local parity
5. broader PR / merge validation only after the fast gates pass

For Python-heavy slices, default to this fast path:

```text
./.venv/bin/python -m black --check <touched-python-files>
./.venv/bin/python -m pytest -x <failing-test-file> -k <failing-test-name>
./.venv/bin/python -m pytest -x <touched-test-files>
./.venv/bin/python ./scripts/local_ci_parity.py --level focused-local --watchdog-seconds 600
```

If `Black` can fail fast, do **not** start with a long watchdog-backed parity run.

### 4. Fix the root cause, not the last visible symptom

A compliant fix should eliminate the underlying mismatch, not merely the most recent assertion line.

Examples of root-cause fixes:

- a formatter failure caused by one overlong assertion expression
- a regression that locks wording the canonical source does not actually guarantee
- a checkpoint/provenance test that expects a required field the workflow contract never declared
- a CI failure that points to the exact failed step and exposes a local-precheck gap

If one failure exposes a deeper contract mismatch, patch the canonical source **and** the regression together.

### 5. No trial-and-error churn

After one failed repair hypothesis:

- gather fresh evidence from the new failing output
- restate the exact failing command/check, relevant error text, and suspected root cause
- only then apply the next patch

Do **not** fix one line, rerun a huge suite, guess, and repeat.
Do **not** widen validation because of habit.
Do **not** narrate stale or assumed state.

### 6. Prefer exact-state inspection over memory

Use the active worktree and the exact current diff.

Prioritize:

- `git status --short --branch`
- `git diff --name-only`
- the exact changed file contents
- the exact failing test output
- the exact failing CI step / job / check metadata

Do **not** rely on memory, earlier summaries, or a stale checkpoint when the user says the output already shows the failure.

### 7. Widen only after the fast gate is green

Only move to the next wider rung after the narrower gate passes.

Correct expansion order:

- file-level fix
- touched-file formatter check
- single failing test / file
- touched-test bundle
- focused local parity
- PR/CI recheck

Incorrect order:

- full suite first
- parity first
- merge/CI polling before local fast gates
- broad repo scans before reading the failing method

## Required Working Method

1. Re-anchor on the active worktree and exact diff.
2. Parse the current failure output.
3. Read the exact failing method / assertion / file before editing.
4. State the exact failing command/check, relevant error text, and suspected root cause.
5. Apply the minimal patch that fixes the root cause.
6. Re-run the narrowest failing gate first.
7. Expand validation only after the narrow gate passes.
8. Update checkpoint / PR state only after the local root cause is actually resolved.

## Fast-Path Defaults

### For formatter-led failures

- run `Black --check` on touched Python files first
- if it fails, inspect `black --diff` or the exact changed lines
- fix formatting before any broader test/parity command

### For single test failures

- run the specific test or test file with `-x`
- inspect the exact failing assertion and the method it exercises
- patch the underlying mismatch, not just the assertion surface

### For CI failures

- inspect the exact failed check/job/step first
- reproduce the equivalent local command on the narrowest relevant surface
- do not infer root cause from workflow title alone

## Output Format

Return results in this structure:

### Active surface

- worktree / branch / issue / PR actually used
- changed files inspected

### Exact failure evidence

- failing command or check
- relevant error text
- failing file / test / method / assertion

### Root cause

- the single best current explanation grounded in the output and source

### Fix applied

- files changed
- why the patch addresses the root cause rather than the last symptom

### Validation ladder

- which fast gate was run first
- which rung passed next
- what remains before merge / completion

## Completion Criteria

This prompt is complete only when:

- the failure is reproduced or parsed from exact current output
- the root cause is stated before the patch
- the first rerun is the narrowest relevant validation gate
- no broad scan or broad parity run was used prematurely
- the final recommendation or next step is based on current evidence, not memory
