# Copilot AI Assistant Workflow Guardrails & Problem-Solving Guidelines

**CRITICAL RULE FOR ALL BUG FIXES & PROBLEM SOLVING:**
Do NOT attempt to solve any problem or apply any bug fix by violating existing project constraints, architectural decisions (ADRs), or established guardrails.

When diagnosing and fixing issues, you must prioritize compliance with the repository's rules over taking the "easiest" or "fastest" path. A solution that breaks an ADR to fix a localized bug is explicitly considered a failure.

## 1. Compliance First over Speed

- **Consult Guardrails Before Fixing:** Before proposing or implementing any fix, you must mentally cross-reference the architecture documentation (`docs/architecture/ADR-*.md`).
- **No Destructive Workarounds:** Do not mutate, ignore, or bypass strict repository contracts (e.g., namespace definitions, installation boundaries like ADR-012, or ephemeral `TMPDIR` constraints) just to unblock an error message.
- **Fail Safe:** If a bug fix requires violating a known constraint or ADR, you must pause, escalate the conflict to the human user, and ask for architectural clarification rather than silently applying the non-compliant fix.

## 2. ADR and Architectural Awareness

- Explicitly check `docs/architecture/` before mutating or refactoring installation paths, namespaces (e.g., `.copilot` vs root rules), communication protocols, or directory boundaries.
- Treat boundaries like the `.copilot` subsystem directory and workspace environmental constraints (`.tmp`, `.factory.env`) as immutable mature structures that the code must defensively adapt to, not things you can discard when convenient.

## 3. Defensive and Resilient Coding

- Mature components expect hostile environments. Do not assume folders (like `.tmp`) haven't been deleted or that environment variables won't behave unexpectedly.
- Write defensive code that seamlessly recovers from transient state loss (e.g., `mkdir -p` before acting) rather than failing the toolchain when things aren't "perfect".

## 4. Release Bump Discipline

- Treat `VERSION` as the canonical release marker.
- If you change `VERSION`, you must also update `CHANGELOG.md`, create or update the matching GitHub release notes file at `.github/releases/v<version>.md`, and refresh `manifests/release-manifest.json`.
- Do **not** update changelog or release notes for ordinary commits unless the user asks for it or `VERSION` changes.
- When preparing a release bump, ensure the changelog contains a dedicated `## [<version>]` section and the GitHub release notes explicitly mention the same version.

Remember: **You solve nothing if you fix one bug by creating architectural debt or violating design guardrails.**
