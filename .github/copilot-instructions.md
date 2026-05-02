# Copilot AI Assistant Workflow Guardrails & Problem-Solving Guidelines

**CRITICAL RULE FOR ALL BUG FIXES & PROBLEM SOLVING:**
Do NOT attempt to solve any problem or apply any bug fix by violating existing project constraints, architectural decisions (ADRs), or established guardrails.

When diagnosing and fixing issues, you must prioritize compliance with the repository's rules over taking the "easiest" or "fastest" path. A solution that breaks an ADR to fix a localized bug is explicitly considered a failure.

## 1. Compliance First over Speed

- **Consult Guardrails Before Fixing:** Before proposing or implementing any fix, you must mentally cross-reference the architecture documentation (`docs/architecture/ADR-*.md`).
- **No Destructive Workarounds:** Do not mutate, ignore, or bypass strict repository contracts (e.g., namespace definitions, installation boundaries like ADR-012, or ephemeral `TMPDIR` constraints) just to unblock an error message.
- **Fail Safe:** If a bug fix requires violating a known constraint or ADR, you must pause, escalate the conflict to the human user, and ask for architectural clarification rather than silently applying the non-compliant fix.
- **Respect ordered-issue checkpoints:** When work is moving through the issue → PR → merge loop, keep `.tmp/github-issue-queue-state.md` current. `resolve-issue`, `pr-merge`, `execute-approved-plan`, and interruption recovery all consume that shared checkpoint; do not invent a second enforcement path or bypass the GitHub-truth evidence (`issue_state`, `pr_state`, `ci_state`, `cleanup_state`, `last_github_truth`).
- **Respect execution surfaces:** Generated-workspace-sensitive tasks belong to the host repository's generated `software-factory.code-workspace` surface (or an explicit companion runtime target), not the source checkout alone. Source-checkout tooling may inspect or point at the companion installed workspace, but it must not invent a second runtime contract or silently pretend that `Host Project (Root)` exists when it does not.
- **Re-anchor before acting on issue work:** Before implementation, validation, or merge narration for any queued issue, read `.tmp/github-issue-queue-state.md`, confirm the active branch/worktree matches that checkpoint, and treat the current editor path as advisory only until that re-anchor is complete.
- **Refuse stray partial `.tmp` snapshots as execution surfaces:** If the current editor/file path points under `.tmp/queue-worktrees/*` but the top-level directory is missing repo/worktree markers such as `.git`, `docs/`, or `scripts/`, treat it as a stray partial snapshot, do **not** continue work from it, and resume from the repository root plus `.tmp/github-issue-queue-state.md`.
- **Do not claim progress from the wrong surface:** If the checkpoint, branch/worktree state, and editor path disagree, stop, re-anchor, and explain the mismatch before running commands, editing files, or narrating issue progress. Do not guess which surface is authoritative.

## 2. ADR and Architectural Awareness

- Explicitly check `docs/architecture/` before mutating or refactoring installation paths, namespaces (e.g., `.copilot` vs root rules), communication protocols, or directory boundaries.
- Treat boundaries like the `.copilot` subsystem directory and workspace environmental constraints (`.tmp`, `.factory.env`) as immutable mature structures that the code must defensively adapt to, not things you can discard when convenient.
- When queue execution or interruption recovery is in play, treat `.tmp/github-issue-queue-state.md` plus a registered git worktree as the canonical execution anchor; a stale editor tab or stray `.tmp` snapshot is never enough evidence to resume work.

## 3. MCP-First Tool Routing

- Broad terminal auto-approval settings do **not** change tool routing priority.
- When an available MCP server can satisfy the task, prefer the most specialized MCP server before generic terminal execution.
- Use the bash gateway only for allowlisted script workflows or when no dedicated MCP capability exists; it is not the default executor for arbitrary commands.
- Treat generic terminal execution as a fallback-only path when no suitable MCP tool can satisfy the task, not as a convenience shortcut.

## 4. Defensive and Resilient Coding

- Mature components expect hostile environments. Do not assume folders (like `.tmp`) haven't been deleted or that environment variables won't behave unexpectedly.
- Write defensive code that seamlessly recovers from transient state loss (e.g., `mkdir -p` before acting) rather than failing the toolchain when things aren't "perfect".
- For generated or rewritten Python source, use the repository's **actual formatter** with an explicit interpreter (`./.venv/bin/python -m black`, `python3 -m black`, or the Black library) before treating the write as complete. Do **not** hand-format Python output, rely on bare `python`, or treat newline-only normalization as a substitute for Black.
- Repo-owned writer surfaces that persist Python files for issue resolution should invoke Black-compatible formatting at save time when formatter-enforced mode is required, so later `black --check` acts as confirmation rather than surprise.

## 5. Release Bump Discipline

- Treat `VERSION` as the canonical release marker.
- If you change `VERSION`, you must also update `README.md` `## Current Release`, `CHANGELOG.md`, create or update the matching GitHub release notes file at `.github/releases/v<version>.md`, and refresh `manifests/release-manifest.json`.
- Do **not** update changelog or release notes for ordinary commits unless the user asks for it or `VERSION` changes.
- When preparing a release bump, ensure the changelog contains a dedicated `## [<version>]` section and the GitHub release notes explicitly mention the same version.
- GitHub release notes should include a `## Delivery status snapshot` table summarizing what the release fulfills, what remains open, and why that boundary matters.
- **Definition of Done:** A release bump is done only when all current-release surfaces (`VERSION`, `README.md` `## Current Release`, `CHANGELOG.md`, `.github/releases/v<version>.md`, and `manifests/release-manifest.json`) agree on the same version, the post-commit release checks pass, and the published GitHub release is cut from the checked-in notes.
- **Quality metric:** Treat release-quality as `current-release surface consistency = 100%` plus `release guardrail pass rate = 100%`; older version strings may remain only in explicit historical sections/files, never on public current-release surfaces.

## 6. Natural-Language Workflow Alias Routing

- Treat `resolve-issue` plus `pr-merge` as the single canonical issue → PR → merge process. `execute-approved-plan` is the bounded multi-issue wrapper over that same process, and `queue-backend` / `queue-phase-2` are scoped manual-checkpoint variants rather than alternate implementation or merge workflows.
- Treat phrases such as `execute the plan`, `continue the plan`, `run the approved queue`, `work through the approved backlog`, or `finish the approved issue set` as workflow-orchestration requests, not generic planning chatter.
- When a finite GitHub-backed issue set, umbrella issue, or queue checkpoint makes the target plan unambiguous, prefer the dedicated `execute-approved-plan` workflow path over ad-hoc conversational planning.
- If more than one plausible plan exists, do not guess which plan the operator means; ask which issue set is approved.
- Do not force these aliases onto single-issue execution requests; those still belong to `resolve-issue`.
- There is no supported global `UserPromptSubmit` workflow hook in this contract. Prompt-time hooks created a second process and must not be reintroduced as issue/merge gatekeepers.

## 7. Workflow Hardening and Deterministic Recovery

- At the start of any issue slice, re-anchor from `.tmp/github-issue-queue-state.md` and fresh GitHub truth before implementation, validation, repair, merge narration, or completion claims.
- prefer `./.venv/bin/python` for repository Python commands. If the repository venv is unavailable for a justified one-off, use explicit `python3`. do **not** use bare `python`.
- Treat `execute-approved-plan` as the generic executor for any approved bounded GitHub-backed issue set, including a single approved issue, an umbrella-derived child issue set, an explicit approved issue list, or a checkpoint-published queue.
- Specialized wrappers such as an umbrella resolver may narrow scope or resolve ordering, but they must not introduce a second execution, merge, repair, or checkpoint path.
- Use bounded waits, explicit watchdog/timeout states, and deterministic stop conditions for CI polling and long-running validation. A pending timeout is a blocker, not permission to keep spinning.
- GitHub fetch/list/view automation must also use bounded watchdogs; do not allow unbounded `gh` fetches or item-enumeration loops to wait until manual interruption.
- Require explicit success or failure evidence from exit status, structured output, validated artifacts, or exact GitHub metadata. Do not infer success from silence, partial logs, or ambiguous output.
- Refresh GitHub truth immediately before readiness, merge, queue-advance, or blocker narration. Do not narrate PR state from memory, stale checkpoint values, earlier terminal output, or terminal silence.
- When a PR exists, require the GitHub PR head branch to match the current local branch and the checkpoint `active_branch`; treat any mismatch as a blocker that requires re-anchor before continuing.
- Inspect the exact failing check, job, and step metadata before deciding on root cause. Do not guess from job titles alone.
- After one failed hypothesis, gather new evidence before applying another code change. Do not fall into trial-and-error churn.
- If parsing, piping, or terminal behavior makes the result ambiguous, stop and report the ambiguity instead of continuing on guessed state.

Remember: **You solve nothing if you fix one bug by creating architectural debt or violating design guardrails.**
