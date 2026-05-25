import re
from typing import Dict, List


def detect_residues(
    issues: List[Dict], prs: List[Dict], branches: List[str] = None
) -> List[str]:
    blockers = []
    issues_by_num = {str(i.get("number")): i for i in issues}
    if branches is None:
        branches = []

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
                f"Open PR #{pr.get('number')} has no linked active issue evidence."
            )
            continue

        issue = issues_by_num.get(str(linked_issue))
        if issue and issue.get("state", "").upper() == "CLOSED":
            blockers.append(
                f"Issue #{linked_issue} is CLOSED but has an open PR #{pr.get('number')}."
            )

    # Check for active branches for closed issues
    for branch in branches:
        match = re.search(r"issue-(\d+)", branch)
        if match:
            linked_issue = match.group(1)
            issue = issues_by_num.get(str(linked_issue))
            if issue and issue.get("state", "").upper() == "CLOSED":
                blockers.append(
                    f"Issue #{linked_issue} is CLOSED but branch '{branch}' is still open."
                )

    return blockers
