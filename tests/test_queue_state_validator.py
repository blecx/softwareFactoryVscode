import json
from pathlib import Path

import jsonschema
import pytest

from scripts.validate_queue_state import validate_queue_state


def test_valid_queue_state():
    # Should not raise exception
    valid_data = {
        "active_issue": "387",
        "execution_lease_id": "ab12",
        "branch": "issue-387-checkpoint-schema",
        "worktree": ".tmp/queue-worktrees/issue-387-checkpoint-schema",
        "status": "in_progress",
        "github_truth_summary": "Issue 387 is open",
    }
    validate_queue_state(valid_data)


def test_missing_required_fields():
    # Missing execution_lease_id, branch, worktree
    invalid_data = {"active_issue": "387"}
    with pytest.raises(SystemExit) as exc_info:
        validate_queue_state(invalid_data)
    assert exc_info.value.code == 1


def test_wrong_type():
    invalid_data = {
        "active_issue": "387",
        "execution_lease_id": "ab12",
        "branch": 123,  # should be string
        "worktree": ".tmp/queue-worktrees/issue-387-checkpoint-schema",
    }
    with pytest.raises(SystemExit) as exc_info:
        validate_queue_state(invalid_data)
    assert exc_info.value.code == 1
