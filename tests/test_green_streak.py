import pytest

from scripts.verify_production_signoff import (
    JobEvidence,
    NormalizedRunEvidence,
    compute_green_streak,
)


def make_run(
    run_id,
    branch="main",
    sha="123",
    status="completed",
    conclusion="success",
    jobs=None,
):
    if jobs is None:
        jobs = [JobEvidence("build", "success")]
    return NormalizedRunEvidence(
        run_id=str(run_id),
        branch=branch,
        head_sha=sha,
        status=status,
        conclusion=conclusion,
        jobs=jobs,
    )


def test_success_success_success():
    history = [make_run(3), make_run(2), make_run(1)]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 3
    assert not blockers


def test_success_failure_success():
    history = [
        make_run(3, conclusion="success"),
        make_run(2, conclusion="failure"),
        make_run(1, conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 1
    assert "Run 2 failed" in str(blockers)


def test_success_success_success_older_failure_does_not_block_required_streak():
    history = [
        make_run(4, conclusion="success"),
        make_run(3, conclusion="success"),
        make_run(2, conclusion="success"),
        make_run(1, conclusion="failure"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 3
    assert not blockers


def test_pending_latest():
    history = [
        make_run(3, status="in_progress", conclusion=""),
        make_run(2, conclusion="success"),
        make_run(1, conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 0
    assert "pending" in str(blockers)


def test_missing_job():
    history = [make_run(2, jobs=[JobEvidence("other", "success")]), make_run(1)]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 0
    assert "missing" in str(blockers)


def test_wrong_branch():
    history = [make_run(3, branch="other-branch"), make_run(2), make_run(1)]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 2
    assert not blockers


def test_wrong_head_sha():
    history = [make_run(2, sha="456"), make_run(1, sha="123")]
    streak, blockers = compute_green_streak(history, "main", "456", ["build"])
    assert streak == 2
    assert not blockers


def test_cancelled_superseded():
    # If a run is cancelled but its SHA differs from target SHA, it's superseded.
    history = [
        make_run(3, sha="456", conclusion="success"),
        make_run(2, sha="123", conclusion="cancelled"),  # superseded
        make_run(1, sha="abc", conclusion="success"),
        make_run(0, sha="def", conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "456", ["build"])
    assert streak == 3
    assert not blockers


def test_cancelled_blocking():
    # If a run is cancelled and its SHA matches target SHA, it's blocking.
    history = [
        make_run(3, sha="123", conclusion="cancelled"),
        make_run(2, sha="abc", conclusion="success"),
        make_run(1, sha="def", conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 0
    assert "cancelled" in str(blockers)


def test_skipped_older_run():
    # Older skipped runs do not interrupt streak evaluation
    history = [
        make_run(4, sha="123", conclusion="success"),
        make_run(3, sha="456", conclusion="success"),
        make_run(2, sha="789", conclusion="skipped"),
        make_run(1, sha="abc", conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 3
    assert not blockers


def test_skipped_latest_run():
    # Latest run skipped and matches target SHA = blocking
    history = [
        make_run(3, sha="123", conclusion="skipped"),
        make_run(2, sha="456", conclusion="success"),
        make_run(1, sha="abc", conclusion="success"),
    ]
    streak, blockers = compute_green_streak(history, "main", "123", ["build"])
    assert streak == 0
    assert "skipped" in str(blockers)
