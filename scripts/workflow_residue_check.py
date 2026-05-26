import re
from typing import Dict, List, Optional


def detect_residues(
    issues: List[Dict],
    prs: List[Dict],
    branches: Optional[List[str]] = None,
    worktrees: Optional[List[str]] = None,
    checkpoint_state: Optional[Dict] = None,
) -> List[str]:
    blockers = []
    issues_by_num = {str(i.get("number")): i for i in issues}
    if branches is None:
        branches = []
    if worktrees is None:
        worktrees = []

    # Map issue numbers to open PRs
    for pr in prs:
        if pr.get("state", "").upper() != "OPEN":
            continue

        linked_issue = None
        head = pr.get("headRefName", "")
        match = re.search(r"issue-(\d+)", head)
        if match:
            linked_issue = match.group(1)

        body = pr.get("body", "")
        if not linked_issue:
            match = re.search(
                r"(?:Resolves|Fixes|Closes)\s+#(\d+)", body, re.IGNORECASE
            )
            if match:
                linked_issue = match.group(1)

        if not linked_issue:
            blockers.append(
                f"Open PR #{pr.get('number')} has no linked active issue evidence. Recommendation: Link an issue or close the PR with 'gh pr close {pr.get('number')}'."
            )
            continue

        issue = issues_by_num.get(str(linked_issue))
        if issue and issue.get("state", "").upper() == "CLOSED":
            blockers.append(
                f"Issue #{linked_issue} is CLOSED but has an open PR #{pr.get('number')}. Recommendation: Close the PR with 'gh pr close {pr.get('number')}'."
            )

    # Check for active branches for closed issues
    for branch in branches:
        match = re.search(r"issue-(\d+)", branch)
        if match:
            linked_issue = match.group(1)
            issue = issues_by_num.get(str(linked_issue))
            if issue and issue.get("state", "").upper() == "CLOSED":
                blockers.append(
                    f"Issue #{linked_issue} is CLOSED but branch '{branch}' is still open. Recommendation: Delete the branch with 'git branch -D {branch}'."
                )

    # Check for active worktrees for closed issues
    for worktree in worktrees:
        match = re.search(r"issue-(\d+)", worktree)
        if match:
            linked_issue = match.group(1)
            issue = issues_by_num.get(str(linked_issue))
            if issue and issue.get("state", "").upper() == "CLOSED":
                blockers.append(
                    f"Issue #{linked_issue} is CLOSED but worktree '{worktree}' is still active. Recommendation: Remove the worktree with 'git worktree remove -f {worktree}'."
                )

    # Check for checkpoint state residue
    if checkpoint_state:
        active_issue = checkpoint_state.get("active_issue")
        if active_issue:
            issue = issues_by_num.get(str(active_issue))
            if issue and issue.get("state", "").upper() == "CLOSED":
                if checkpoint_state.get("status") == "working":
                    blockers.append(
                        f"Issue #{active_issue} is CLOSED but checkpoint state claims active execution. Recommendation: Update '.tmp/github-issue-queue-state.md' to clear the active issue or run a sync."
                    )

    return blockers
