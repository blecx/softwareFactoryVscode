# ADR-013: Architecture Authority and Plan Separation

## Status

Accepted

## Context

The repository uses several kinds of documents that look similar during review but serve different purposes:

- accepted ADRs that define architecture rules and guardrails,
- maintained architecture synthesis documents that explain how multiple ADRs fit together,
- implementation plans that sequence work and hardening steps,
- and derived operator documents such as installation guides, handouts, and cheat sheets.

Without an explicit authority hierarchy, implementation plans can accidentally start redefining architecture terms, maintained synthesis documents can drift into competing sources of truth, and derived documents can be mistaken for normative guardrails.

That ambiguity is especially risky for terms such as `installed`, `running`, and `active`, where implementation details, operator guidance, and architecture constraints all need to stay aligned without letting planning documents silently redefine the architecture.

The same risk now applies to AI-facing markdown surfaces such as `.copilot/skills/*`, `.github/prompts/*`, `.github/agents/*`, and maintainer/reference docs. Without an ADR-backed precedence order and approved form matrix, thin discovery wrappers or workflow summaries can accidentally look like architecture owners.

## Decision

We adopt an explicit document-authority hierarchy.

### 1. Accepted ADRs are the normative source of architecture guardrails

- **Rule:** Accepted ADRs define architecture rules, terminology, and guardrails.
- **Rule:** Terms that matter architecturally (for example `installed`, `running`, `active`, canonical runtime ownership, or tenancy promotion rules) MUST be defined in accepted ADRs rather than in plans or derived operator docs.
- **Rule:** Architectural changes MUST be reflected by explicitly updating the relevant ADRs; plans or synthesis documents MUST NOT be used to smuggle in architecture changes implicitly.

### 2. Architecture synthesis documents may explain, but not override

- **Rule:** Maintained architecture synthesis documents may consolidate multiple ADRs, map them onto current implementation, and explain future-work boundaries.
- **Rule:** A synthesis document MUST identify itself as non-normative if it is not itself an ADR.
- **Rule:** When a synthesis document lags, accepted ADRs remain authoritative for guardrails and terminology.

### 3. Implementation plans are authoritative only for sequencing and hardening work

- **Rule:** An implementation plan is the source of truth for sequencing, delivery phases, hardening steps, and implementation backlog within the bounds set by the architecture.
- **Rule:** A plan MUST reference accepted ADRs for terminology and architecture constraints rather than redefining them.
- **Rule:** Plans may describe implementation targets and gaps, but they MUST NOT claim to be the normative source of architecture truth.

### 4. Derived operator documents are non-normative projections

- **Rule:** Documents such as installation guides, handouts, and cheat sheets are derived operator-facing material.
- **Rule:** Derived documents MUST follow accepted ADRs and the verified implementation, but they are not themselves architecture sources of truth.
- **Rule:** If a derived document conflicts with an accepted ADR, the derived document must be corrected rather than treated as an architecture override.

### 5. When implementation and architecture drift, resolve it explicitly

- **Rule:** If verified implementation has intentionally moved beyond the current ADR wording, the ADRs must be updated explicitly so the architecture remains reviewable and auditable.
- **Rule:** If implementation conflicts with an accepted ADR unintentionally, the implementation must be treated as drift until an explicit architectural decision says otherwise.
- **Rule:** Plans and synthesis documents may describe the mismatch, but they MUST NOT resolve the mismatch by redefining architecture terms on their own.

### 6. AI-facing markdown must use one ADR-backed authority chain and one approved form matrix

- **Rule:** For AI-facing markdown, accepted ADRs are priority 1 for architecture rules, terminology, precedence, and canonical-form ownership.
- **Rule:** The precedence order for AI-facing surfaces is:
  1. accepted ADRs;
  2. `.github/copilot-instructions.md` as the repo-wide behavioral projection of those ADRs;
  3. canonical workflow skills under `.copilot/skills/*` for operational mechanics;
  4. prompt and agent wrappers under `.github/prompts/*` and `.github/agents/*` as activation/discovery surfaces only; and
  5. maintainer/reference docs under `docs/maintainer/` as non-normative indexes, maps, and runbooks.
- **Rule:** Lower-ranked surfaces may summarize, delegate, or enforce, but they MUST NOT redefine architecture terms, precedence, or canonical-form ownership.

#### Approved AI-surface canonical form matrix

| Canonical form | Shape | Allowed surface families | Notes |
| --- | --- | --- | --- |
| Form A — authority markdown | plain Markdown with standard headings and links; no prompt metadata block or runtime wrapper | accepted ADRs, maintainer/reference docs, operator runbooks | An accepted ADR is normative; non-ADR docs in this form remain explanatory only. |
| Form B — structured module | YAML frontmatter followed by Markdown sections | `.github/prompts/*`, canonical `.copilot/skills/*`, and frontmatter-based agent wrappers such as `.github/agents/close-issue.md` | Use for operational modules or thin wrappers that do not need embedded `chatagent` metadata. |
| Form C — `chatagent` discovery wrapper | thin Markdown wrapper that contains a fenced `chatagent` metadata block plus brief routing sections | `.github/agents/*` wrappers that participate in VS Code custom-agent discovery/runtime behavior | Preserve existing `chatagent` fences unless an accepted ADR explicitly changes that discovery contract. |
| Form D — thin discoverability card | minimal frontmatter plus a short delegation body | alias/namespace wrappers such as `.github/agents/blecs/*`, `.github/agents/speckit/*`, or other non-canonical discovery stubs | These cards may point at the canonical wrapper or skill, but they MUST NOT become the canonical owner of workflow rules. |

- **Rule:** Historical hybrids such as embedded `<skill>` wrappers, duplicated headings, or mixed metadata patterns are drift to normalize, not new approved forms.

## Consequences

- Reviewers can distinguish architecture guardrails from implementation sequencing.
- Plans can remain actionable without becoming shadow architecture documents.
- Derived operator docs can be rewritten aggressively to reflect current behavior without threatening architectural authority.
- Future terminology disputes can be resolved by pointing to one accepted ADR rather than debating which planning or guidance document "won."
- AI-facing markdown can now be normalized against one approved precedence chain and one approved form matrix without guessing which wrapper or doc "won."
