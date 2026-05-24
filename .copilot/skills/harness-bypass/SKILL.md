# Harness Bypass Skill

This skill defines the safe execution protocol for the `harness-bypass-resolution` agent when overriding standard repository governance.

## 1. Mechanical Bypass Authorization
Accidental or agent-delegated bypass activation is forbidden. Before making any destructive or bypass changes, you **must** call the bypass guard script to log the reason and provide the explicit human confirmation evidence. The user must provide the literal token `I_AUTHORIZE_BYPASS` in their environment.

```bash
# If the agent attempts to run this without human confirmation, it will mechanically fail.
# The user must make sure HARNESS_BYPASS_ACK is set if they approve.
env HARNESS_BYPASS_ACK="I_AUTHORIZE_BYPASS" ./scripts/harness_bypass_guard.py --reason "<reason here>"
```
If this script rejects the bypass, ABORT immediately and ask the user to authorize.

## 2. Execute the Bypass Action
You are authorized to use terminal commands that standard agents cannot use:
- `gh pr merge <PR> --squash --admin`
- `gh issue close <ISSUE>`
- `git push -u origin <BRANCH>`
- `git commit --allow-empty -m "chore: force override"`

Do not attempt to run `scripts/local_ci_parity.py` or `.vscode/tasks.json` validation checks if the operator invoked this bypass to skip them.

## 3. Reset the Queue State
After resolving the stuck PR or issue, you must reset the tracking checkpoint so standard agents don't panic on the next task.
```bash
echo "{}" > .tmp/github-issue-queue-state.json # Or reset equivalent .md if used
rm -f .tmp/github-issue-queue-state.md
```
Or rewrite `.tmp/github-issue-queue-state.md` to indicate a clean slate ready for the next issue.
Always ensure the active branch is checked out to `main` and fully synced (`git checkout main && git pull`).

## 4. Post-Condition
Report to the operator that the issue was bypassed successfully, why it was bypassed, and that the queue state is clean.
