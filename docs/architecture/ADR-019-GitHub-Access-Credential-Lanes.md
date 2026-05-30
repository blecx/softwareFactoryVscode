# ADR-019: GitHub Access Credential Lanes

## Status

Accepted

## Context

- The software factory requires standardized and secure methods for interacting with Git and the GitHub API to avoid inventing a secondary credential authority.
- Consistency must be maintained with established architectural rules, citing ADR-006, ADR-012, ADR-013, ADR-014, and ADR-015 where execution and workspace boundaries matter.
- Downstream AI-facing surfaces will project these rules to ensure predictable, secure credential handling across factory boundaries.

## Decision

### 1. Git Transport Lane

- **Rule:** SSH remote transport via `ssh-agent` is the enforced default execution state for Git operations.

### 2. Git Signing Lane

- **Rule:** `FACTORY_GIT_SIGNING_PRIORITY=ssh,gpg` is the default. Setting `gpg,ssh` makes GPG the primary signing method.

### 3. GitHub API Lane

- **Rule:** GitHub API operations continue to require specialized token/gh/GitHub-App-style credentials, isolated from Git transport credentials.

### 4. Secret Containment

- **Rule:** Private key storage in the repository or within `.factory.env` is explicitly forbidden.
- **Rule:** Default keyring mounts into targeted factory containers is forbidden.

### 5. Authority / precedence

- **Rule:** This ADR is the authoritative decision regarding Git transport, typing, and API credential scopes.
- **Rule:** Lower-ranked docs and workflow surfaces must project but never redefine this access policy.

### 6. Canonical form / contract

- **Rule:** All credential, container auth, and environment secret-handling artifacts must align strictly with the three defined lanes.
- **Affected surface families:** ADRs | maintainer docs | prompts | skills | agent wrappers | template injection points

### 7. Runtime / discovery preservation

- **Rule:** Preserve any current discovery syntax (for example `chatagent` fences or other active wrapper markers) until this ADR explicitly replaces it.

## Downstream projections

- `docs/SETUP-GITHUB-REPOSITORY.md` (to be created or updated later)
- `.copilot/skills/` access patterns

## Consequences

- We leverage the host environment's existing ssh-agent securely without duplicating secret management logic.
- Accidental footprint leakage is prevented by forbidding `.factory.env` key storage and avoiding default keyring mounts to child containers.

