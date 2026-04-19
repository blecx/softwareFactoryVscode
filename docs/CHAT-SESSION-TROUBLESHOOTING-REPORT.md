# Chat session troubleshooting report

This document is the repo-owned problem inventory and closure record for umbrella issue `#61`.

It captures the workflow failures that motivated the hardening program and records the final default-branch recheck after child issues `#62`-`#65` landed.

## Historical problem inventory

The mitigation program started because earlier chat-driven issue execution was still vulnerable to four recurring failure modes:

1. **Workflow drift and premature completion claims**
   - Problem: advisory docs were not enough to stop completion narration from drifting ahead of live GitHub truth.
   - Child slice: `#62`.
2. **Interruption recovery gaps**
   - Problem: recovery after compaction, restart, or timeout depended too heavily on transcript archaeology instead of repo-owned state.
   - Child slice: `#63`.
3. **Wrong execution-surface choices**
   - Problem: generated-workspace-sensitive operations could still be launched from the source checkout without a clear rejection path.
   - Child slice: `#64`.
4. **Non-interactive terminal and GitHub CLI traps**
   - Problem: pager/watch churn, false prompt detection, and broken stdin pipelines caused avoidable reruns and planning failures.
   - Child slice: `#65`.

## Child-slice resolution map

| Risk area | Child issue | Before implementation | Default-branch outcome |
| --- | --- | --- | --- |
| Deterministic GitHub-truth enforcement | `#62` | Partially resolved | Resolved with repo-owned queue enforcement, GitHub-truth checkpoint requirements, and regression coverage |
| Interruption recovery and repo-side diagnostics | `#63` | Unresolved | Resolved with repo-owned recovery prompts/skills, `.tmp/interruption-recovery-snapshot.md`, and snapshot helper coverage |
| Execution-surface routing | `#64` | Partially resolved | Resolved for the supported workflow boundary with explicit wrong-surface rejection and routing guidance |
| Non-interactive terminal / GitHub CLI automation safety | `#65` | Unresolved | Resolved with pager-free JSON polling guidance, `scripts/noninteractive_gh.py`, and stdin-safe shell composition rules |

## Child-issue contract audit

Each umbrella child issue body on GitHub now includes the workflow fields that `#61` required:

- an explicit **Current environment status before implementation** statement
- a **Definition of Done** section
- a **Quality checks** section
- a scoped workflow/runtime contract description

That contract audit applies to issues `#62`, `#63`, `#64`, and `#65`.

## Final environment recheck on 2026-04-19

After `#62`-`#65` landed on `main`, the current environment was rerun against the final state.

### Local CI parity

- Command: `./.venv/bin/python ./scripts/local_ci_parity.py`
- Result: `210 passed, 2 skipped`
- Boundary note: only the documented default warning remained because Docker image build parity is opt-in for local runs.

### Wrong-surface rejection smoke

- Command: `./.venv/bin/python ./scripts/workspace_surface_guard.py verify-runtime-mcp --target '${workspaceFolder:Host Project (Root)}' > ./.tmp/issue61_surface.out 2>&1`
- Result: exit code `2`
- Expected behavior observed: the helper rejected source-checkout invocation and explained that the action belongs to the generated `software-factory.code-workspace` surface backed by companion runtime metadata.

### Non-interactive GitHub polling smoke

- Command: `./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks 69 | ./.venv/bin/python -c "import json, sys; data = json.load(sys.stdin); print(data['summary']['overall']); print(data['summary']['total'])"`
- Result: `success` then `4`
- Expected behavior observed: pager-free JSON polling worked without watch-mode churn and without the heredoc/stdin trap.

## Final status

Umbrella issue `#61` is satisfied when interpreted against the default branch as of `2026-04-19`:

- all child issues `#62`-`#65` landed on `main`
- the child issues record the required Definition of Done / quality-check / current-environment context
- the final environment recheck was rerun against the merged state

This report should be treated as the canonical repo-side explanation of the chat-session workflow failures that motivated the mitigation program and the evidence that those mitigations are now in place.
