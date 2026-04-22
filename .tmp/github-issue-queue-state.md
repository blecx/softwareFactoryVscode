# GitHub Issue Queue State

- queue: 88 -> 89 -> 90 -> 91 -> 92
- active_issue: 88
- active_branch: issue-88-bounded-suspend-resume
- active_pr: none
- status: validated-local
- last_validation: `./.venv/bin/python ./scripts/local_ci_parity.py` ✅ (`244 passed, 3 skipped`; docker image build parity skipped by default)
- next_gate: create and publish a PR for issue #88 from `issue-88-bounded-suspend-resume`, then continue with GitHub-truth review/merge flow without pausing locally
- blocker: none
- issue_state: open-verified-on-github
- pr_state: none
- ci_state: not-applicable
- cleanup_state: clean-verified-pre-implementation
- last_github_truth: issue #87 is closed and PR #96 merged at 2026-04-21T21:15:08Z; refreshed open-issue truth shows #88 (`feat: implement bounded suspend/resume lifecycle semantics for the MCP runtime`) as the next executable queue item and local branch `issue-88-bounded-suspend-resume` is active from updated `main`
