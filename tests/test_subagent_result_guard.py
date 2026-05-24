import pytest

from scripts.subagent_result_guard import SubagentNoOpError, SubagentResultGuard


def test_rejects_empty():
    with pytest.raises(SubagentNoOpError, match="Result is empty"):
        SubagentResultGuard.validate_result("")
    with pytest.raises(SubagentNoOpError, match="Result is empty"):
        SubagentResultGuard.validate_result("   \n  ")


def test_accepts_valid_json_success():
    payload = '{"issue_number": 429, "status": "SUCCESS"}'
    result = SubagentResultGuard.validate_result(payload)
    assert result["issue_number"] == 429
    assert result["status"] == "SUCCESS"
    assert result["blocker_evidence"] is None


def test_accepts_valid_json_blocker():
    payload = '{"issue": "429", "blocker_evidence": "Tests failed"}'
    result = SubagentResultGuard.validate_result(payload)
    assert result["issue_number"] == "429"
    assert result["status"] is None
    assert result["blocker_evidence"] == "Tests failed"


def test_rejects_missing_issue_json():
    payload = '{"status": "SUCCESS"}'
    with pytest.raises(SubagentNoOpError, match="missing required field: issue_number"):
        SubagentResultGuard.validate_result(payload)


def test_rejects_missing_evidence_json():
    payload = '{"issue_number": 429}'
    with pytest.raises(SubagentNoOpError, match="missing required evidence"):
        SubagentResultGuard.validate_result(payload)


def test_accepts_valid_text_success():
    payload = "Here is the result.\nIssue: #429\nStatus: SUCCESS\nAll good."
    result = SubagentResultGuard.validate_result(payload)
    assert result["issue_number"] == 429
    assert result["status"] == "SUCCESS"


def test_accepts_valid_text_blocker():
    payload = (
        "We are stuck.\nIssue number: 429\nBlocker evidence: API is down\nPlease fix."
    )
    result = SubagentResultGuard.validate_result(payload)
    assert result["issue_number"] == 429
    assert result["blocker_evidence"] == "API is down"


def test_rejects_invalid_text():
    payload = "I fixed the issue, tests passed."
    with pytest.raises(
        SubagentNoOpError, match="Could not parse required JSON or text"
    ):
        SubagentResultGuard.validate_result(payload)
