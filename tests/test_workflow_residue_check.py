from scripts.workflow_residue_check import detect_residues


def test_clean_fixtures():
    issues = [{"number": 1, "state": "OPEN"}]
    prs = [
        {"number": 10, "state": "OPEN", "headRefName": "issue-1", "body": "Resolves #1"}
    ]
    blockers = detect_residues(issues, prs)
    assert len(blockers) == 0


def test_closed_issue_with_open_pr():
    issues = [{"number": 2, "state": "CLOSED"}]
    prs = [
        {"number": 20, "state": "OPEN", "headRefName": "issue-2", "body": "Resolves #2"}
    ]
    blockers = detect_residues(issues, prs)
    assert len(blockers) == 1
    assert "CLOSED but has an open PR #20" in blockers[0]


def test_open_pr_with_no_linked_issue():
    issues = []
    prs = [
        {
            "number": 30,
            "state": "OPEN",
            "headRefName": "feature-branch",
            "body": "No issue linked",
        }
    ]
    blockers = detect_residues(issues, prs)
    assert len(blockers) == 1
    assert "Open PR #30 has no linked active issue evidence" in blockers[0]


def test_closed_issue_with_open_branch():
    issues = [{"number": 3, "state": "CLOSED"}]
    branches = ["issue-3", "main"]
    blockers = detect_residues(issues, [], branches)
    assert len(blockers) == 1
    assert "CLOSED but branch 'issue-3' is still open" in blockers[0]


def test_closed_issue_with_worktree_and_checkpoint():
    issues = [{"number": 4, "state": "CLOSED"}]
    worktrees = ["/tmp/q/issue-4"]
    checkpoint = {"active_issue": 4, "status": "working"}
    blockers = detect_residues(issues, [], [], worktrees, checkpoint)
    assert len(blockers) == 2
    assert any("worktree '/tmp/q/issue-4' is still active" in b for b in blockers)
    assert any("claims active execution" in b for b in blockers)
