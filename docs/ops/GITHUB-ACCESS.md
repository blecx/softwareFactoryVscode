# GitHub Access Setup and Troubleshooting

This runbook is a derived operator guide for the GitHub access credential lanes defined by [`ADR-019`](../architecture/ADR-019-GitHub-Access-Credential-Lanes.md).

Accepted ADRs are authoritative. This page projects those rules into practical operator steps and troubleshooting checks; it does **not** redefine transport, signing, or API credential policy.

## Lane 1: Git transport over SSH via ssh-agent

### Expected state

- `origin` uses SSH (`git@github.com:<owner>/<repo>.git`).
- `ssh-agent` is available in the active shell (`SSH_AUTH_SOCK` is present).
- The agent has at least one loaded key.
- GitHub accepts the key for SSH auth.

### Validate transport lane

- `git remote get-url origin`
- `ssh-add -l`
- `ssh -T git@github.com`
- `./.venv/bin/python ./scripts/github_access.py status --json`

### Common transport failures

- HTTPS remote (`https://github.com/...`) instead of SSH.
- Missing `SSH_AUTH_SOCK` (agent not forwarded/started).
- `ssh-add -l` reports no keys.
- GitHub key not registered for the current account.

## Lane 2: Commit/tag signing priority

`ADR-019` separates signing from transport. Transport can be healthy while signing is blocked.

### Default profile (SSH-first)

- `FACTORY_GIT_SIGNING_PRIORITY=ssh,gpg`
- Prefer SSH signing; fallback to GPG if SSH signing is unavailable.

### Alternate profile (GPG-first)

- `FACTORY_GIT_SIGNING_PRIORITY=gpg,ssh`
- Prefer GPG signing; fallback to SSH signing if GPG is unavailable.

### Validate signing lane

- `git config --get commit.gpgsign`
- `git config --get gpg.format`
- `git config --get gpg.ssh.allowedSignersFile`
- `./.venv/bin/python ./scripts/github_access.py status --json`

### Common signing failures

- Signing is enabled but `user.signingkey` is not configured for the active method.
- SSH signing selected but no allowed signers file/path is configured.
- GPG signing selected but local secret key is missing or unusable.

## Lane 3: GitHub API credentials (token/gh fallback)

GitHub API credentials are isolated from SSH transport and signing.

### Supported readiness signals

- `gh auth status` reports authenticated.
- Or token env vars are set for the active process (`GITHUB_TOKEN`, `GH_TOKEN`, or `GITHUB_PAT`).
- `./.venv/bin/python ./scripts/github_access.py status --json` reports the `github_api` lane as ready.

### SSO notes

If your organization enforces SSO, a token may exist but remain unusable until it is explicitly authorized for the organization. Re-check with `gh auth status` or a scoped API call after SSO authorization.

### Common API credential failures

- `gh` is not installed.
- `gh auth status` fails because login was never completed.
- Token exists but is expired, revoked, or missing required scopes.
- SSO authorization is required but not completed.

## What chat sessions can do vs explicit operator action

Chat sessions can inspect and report state (for example through `scripts/github_access.py status`) and can explain remediation paths.

The following remain explicit operator actions:

- Adding/removing SSH or GPG keys in local key stores.
- Registering/authorizing keys or tokens in GitHub.
- Running `gh auth login` with interactive authentication.
- Completing organization SSO authorization for token use.

## Secret-handling reminders

- Never commit private keys or tokens.
- Never place private keys in `.factory.env`.
- Treat keyring mounts into targeted runtime containers as forbidden unless an accepted ADR explicitly allows them.

## Related references

- [`ADR-019`](../architecture/ADR-019-GitHub-Access-Credential-Lanes.md)
- [`../setup-github-repository.md`](../setup-github-repository.md)
- [`../../scripts/github_access.py`](../../scripts/github_access.py)
