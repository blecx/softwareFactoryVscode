# Harness Bypass Skill

This skill defines the safe execution protocol for the `harness-bypass-resolution` agent when overriding standard repository governance.

## 1. Log the Bypass Reason
Before making any destructive or bypass changes, you **must** log the reason for the bypass to `.tmp/emergency-bypass.log`.
```bash
echo "$(date -Is) - BYPASS REASON: <reason here>" >> .tmp/emergency-bypass.log
```

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
