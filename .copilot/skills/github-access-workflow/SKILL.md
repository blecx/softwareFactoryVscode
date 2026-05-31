---
name: github-access-workflow
description: "Provides context and instructions to verify and guide GitHub SSH, GPG, and API token setup."
---

# GitHub Access Workflow

## Objective
Provides context and instructions for the `github-access-workflow` skill module to verify and guide GitHub SSH, GPG, and API token setup.

## When to Use
- The user asks to verify GitHub access in the terminal or workspace.
- The user asks for help with SSH, GPG, or API token setup for GitHub.
- An operation fails due to missing or invalid GitHub credentials.

## When Not to Use
- Do not use this when the user is asking about general git operations that are unrelated to credential errors or access setup.
- Do not use this to bypass the standard install verifier script.

## Required Sources
- `docs/ops/GITHUB-ACCESS.md`
- `docs/architecture/ADR-019-GitHub-Access-Credential-Lanes.md`

## Constraints
- Run or read evidence from the standard verifier (`python3 scripts/workspace_surface_guard.py verify-github-access`).
- Avoid secret leakage in chat or logs; never print or request raw token secrets.
- Follow ADR-019 boundaries for permitted credential lanes.
- Delegate to `python3 scripts/workspace_surface_guard.py setup-github-access-guided` if the user requires interactive setup.

## Completion Contract
Return a concise summary of the verification status, any specific issues found, and the required next steps or interactive setup commands without logging secrets.
