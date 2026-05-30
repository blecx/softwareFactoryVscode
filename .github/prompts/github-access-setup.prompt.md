---
name: github-access-setup
description: "Prompt to verify and guide GitHub SSH/GPG/API access setup."
---

# GitHub Access Setup

## Objective
Activates the GitHub access workflow to verify or configure SSH, GPG, and API tokens.

## When to Use
- "token refresh broken"
- "SSH/GPG setup"
- "verify GitHub access"

## When Not to Use
- For general repository queries or git operations without credential issues.

## Required Sources
- `.copilot/skills/github-access-workflow/SKILL.md`

## Constraints
- Delegate all credential-verification logic directly to the canonical `github-access-workflow` skill.
- Maintain ADR-013 Form B boundaries without duplicating architecture rules.

## Completion Contract
Hands off execution to the `github-access-workflow` skill and reports the final verification result to the user.
