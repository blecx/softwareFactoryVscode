import json
import os
import tempfile
from typing import Any, Dict
from unittest.mock import patch

import pytest

from scripts.production_readiness_evidence import aggregate_evidence


@pytest.fixture
def valid_review_input() -> Dict[str, Any]:
    traceability = {str(i): "Valid evidence" for i in range(1, 10)}
    return {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": traceability,
        "signoff_evidence": "verified",
        "green_streak_count": 3,
    }


@pytest.fixture
def valid_signoff_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as f:
        json.dump(
            {
                "command": "test",
                "status": "success",
                "timestamp": "2026-01-01",
                "evidence": "xyz",
            },
            f,
        )
        filepath = f.name
    yield filepath
    os.remove(filepath)


def test_aggregate_evidence_success(valid_review_input, valid_signoff_file):
    result = aggregate_evidence(valid_review_input, valid_signoff_file)
    assert result["ready"] is True
    assert len(result["blockers"]) == 0
    assert result["signoff_valid"] is True
    assert result["score_readiness"]["score_inputs"]["docs"] is True


def test_aggregate_evidence_missing_signoff(valid_review_input):
    result = aggregate_evidence(valid_review_input, "non_existent_file.json")
    assert result["ready"] is False
    assert "No production signoff evidence found" in result["blockers"][0]
    assert result["signoff_valid"] is False


def test_aggregate_evidence_traceability_gap(valid_review_input, valid_signoff_file):
    valid_review_input["traceability"]["5"] = "Evidence gap"
    result = aggregate_evidence(valid_review_input, valid_signoff_file)
    assert result["ready"] is False
    assert any("Evidence gap" in b for b in result["blockers"])


@pytest.fixture
def valid_ci_evidence() -> Dict[str, Any]:
    return {
        "run_id": "12345",
        "head_sha": "abcdef123456",
        "job_name": "production-validation",
        "conclusion": "success",
    }


@patch("scripts.production_readiness_evidence.verify_ci_evidence")
def test_aggregate_evidence_ci_evidence_success(
    mock_verify, valid_review_input, valid_ci_evidence
):
    mock_verify.return_value = {"valid": True, "blockers": []}
    result = aggregate_evidence(
        valid_review_input, "non_existent_file.json", ci_evidence=valid_ci_evidence
    )
    assert result["ready"] is True
    assert result["signoff_valid"] is True
    assert len(result["blockers"]) == 0
    assert result["references"]["source"] == "github-ci"
    assert result["references"]["ci_evidence"] == valid_ci_evidence


@patch("scripts.production_readiness_evidence.verify_ci_evidence")
def test_aggregate_evidence_ci_evidence_failure(mock_verify, valid_review_input):
    invalid_ci = {
        "run_id": "12345",
        "head_sha": "abcdef123456",
        "conclusion": "failed",
    }
    mock_verify.return_value = {
        "valid": False,
        "blockers": [
            "Missing required CI field: 'run_url'",
            "CI signoff conclusion is not success",
        ],
    }
    result = aggregate_evidence(
        valid_review_input, "non_existent_file.json", ci_evidence=invalid_ci
    )
    assert result["ready"] is False
    assert result["signoff_valid"] is False
    assert len(result["blockers"]) > 0
    assert any("Missing required CI field: 'run_url'" in b for b in result["blockers"])
    assert any("CI signoff conclusion is not success" in b for b in result["blockers"])
