# Approval profiles reference

This page is a maintainer-facing reference for the repository's current approval-profile surface.
It is an index/reference, not a competing normative authority.
The actual approval behavior lives in the checked-in profile/config files, workspace tasks, and repository instructions.

## Canonical source files

Start with these files when you need to verify or adjust approval behavior:

- [`.copilot/config/vscode-approval-profiles.json`](../../.copilot/config/vscode-approval-profiles.json) — canonical named profile definitions for `chat.tools.subagent.autoApprove` and `chat.tools.terminal.autoApprove`.
- [`.vscode/tasks.json`](../../.vscode/tasks.json) — maintainer-facing workspace tasks that expose the three profile names.
- [`../../scripts/setup-low-approval.sh`](../../scripts/setup-low-approval.sh) — profile selector wrapper used by the workspace tasks.
- [`../../scripts/setup-vscode-agent-settings.py`](../../scripts/setup-vscode-agent-settings.py) — projects the non-approval agent settings and intentionally leaves the `chat.tools.subagent.autoApprove` and `chat.tools.terminal.autoApprove` keys to the approval-profile surface.
- [`../../configs/bash_gateway_policy.default.yml`](../../configs/bash_gateway_policy.default.yml) — default bash-gateway script policy; related to command execution posture, but separate from the VS Code approval-profile JSON.
- [`../../.github/copilot-instructions.md`](../../.github/copilot-instructions.md) — repository-wide behavior guardrails and tool-routing expectations.

## Current profiles

| Profile | Practical posture | What it currently auto-approves | Use this when |
| --- | --- | --- | --- |
| `safe` | Lowest-trust / most conservative workflow posture | A narrow set of subagents (`Plan`, `create-issue`, `close-issue`) plus basic read/test/GitHub CLI terminal commands | You want the smallest default allowlist and expect implementation, merge, or broader terminal work to keep prompting for approval |
| `trusted-workflow` | Canonical maintainer workflow posture | The core implementation/merge subagents (`resolve-issue`, `pr-merge`, `execute-approved-plan`, `ralph-agent`) plus a bounded allowlist of git, Python, Docker, npm, and repo workflow commands | You are running the canonical issue → PR → merge flow and want fewer approval interruptions without switching to blanket command approval |
| `low-friction` | Highest-trust / lowest-friction posture | Additional workflow/factory agents (`workflow`, `factory-operator`, `queue-backend`, `queue-phase-2`, and others) plus regex-based near blanket terminal approval | You intentionally want a high-trust session and accept that the approval barrier is dramatically reduced |

## How the workspace surfaces these profiles

The repository currently exposes three matching task labels in [`.vscode/tasks.json`](../../.vscode/tasks.json):

- `⚙️ Configure Approval Profile (Safe)`
- `⚙️ Configure Approval Profile (Trusted Workflow)`
- `⚙️ Configure Approval Profile (Low-Friction)`

Those tasks route through [`../../scripts/setup-low-approval.sh`](../../scripts/setup-low-approval.sh), which selects the `safe`, `trusted-workflow`, or `low-friction` profile name for the source checkout.

## What this page does and does not mean

- This page explains the currently configured approval profiles; it does **not** authorize changing their behavior.
- If you need to review which workflow/agent surfaces those profiles matter to, pair this page with [`AGENT-ENFORCEMENT-MAP.md`](AGENT-ENFORCEMENT-MAP.md) and [`../WORK-ISSUE-WORKFLOW.md`](../WORK-ISSUE-WORKFLOW.md).
- If you need to change the actual profile behavior, update the canonical config/scripts directly and keep the maintainer docs descriptive of the verified result.
