import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from scripts.verify_production_signoff import verify_signoff


def test_missing_file():
    result = verify_signoff(".tmp/non-existent-file.json")
    assert not result["valid"]
    assert "No production signoff evidence found" in result["blockers"][0]


def test_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("{ not valid json ")
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "is not valid JSON" in result["blockers"][0]
    finally:
        os.unlink(filepath)


def test_missing_required_fields():
    data = {
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        # missing command and evidence
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        blockers = " ".join(result["blockers"])
        assert "Missing required field: 'command'" in blockers
        assert "Missing required field: 'evidence'" in blockers
    finally:
        os.unlink(filepath)


def test_unsuccessful_status():
    data = {
        "command": "run_signoff",
        "status": "failed",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "Signoff status is not success: failed" in result["blockers"]
    finally:
        os.unlink(filepath)


def test_valid_signoff():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True, "implementation": True, "validation": True},
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert result["valid"]
        assert len(result["blockers"]) == 0
    finally:
        os.unlink(filepath)


def test_secret_in_key():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "api_key": "some-value",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert (
            "Key 'api_key' looks like a secret but has unredacted value."
            in result["blockers"]
        )
    finally:
        os.unlink(filepath)


def test_secret_in_value():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "some_data": "ghp_123456789012345678901234567890123456",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "Value at 'some_data' looks like a secret." in result["blockers"]
    finally:
        os.unlink(filepath)


def test_safe_secret_key():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "api_key": "redacted",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert result["valid"]
    finally:
        os.unlink(filepath)


from scripts.verify_production_signoff import verify_ci_evidence


@patch("subprocess.run")
def test_verify_ci_evidence_success(mock_run):
    gh_out = {
        "headSha": "abcdef123456",
        "conclusion": "success",
        "status": "completed",
        "jobs": [
            {
                "name": "production-validation",
                "conclusion": "success",
                "status": "completed",
            }
        ],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef123456",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "production-validation", "conclusion": "success"}],
    }
    result = verify_ci_evidence(ci_evidence, ["production-validation"])
    assert result["valid"] is True
    assert len(result["blockers"]) == 0


def test_verify_ci_evidence_missing_fields():
    ci_evidence = {
        "run_id": "12345",
        "jobs": [{"name": "production-validation", "conclusion": "success"}],
    }
    result = verify_ci_evidence(ci_evidence)
    assert result["valid"] is False
    assert any("Missing required field: 'head_sha'" in b for b in result["blockers"])
    assert any("Missing required field: 'run_url'" in b for b in result["blockers"])


@patch("subprocess.run")
def test_verify_ci_evidence_failure_conclusion(mock_run):
    gh_out = {
        "headSha": "abcdef",
        "conclusion": "success",
        "status": "completed",
        "jobs": [{"name": "job", "conclusion": "failure", "status": "completed"}],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "job", "conclusion": "failure"}],
    }
    result = verify_ci_evidence(ci_evidence, ["job"])
    assert result["valid"] is False
    assert any(
        "Required job 'job' did not succeed (conclusion: failure)" in b
        or "CI signoff conclusion is not success: failure for provided job job" in b
        for b in result["blockers"]
    )


@patch("subprocess.run")
def test_verify_ci_evidence_with_secrets(mock_run):
    gh_out = {
        "headSha": "abcdef",
        "conclusion": "success",
        "status": "completed",
        "jobs": [{"name": "job", "conclusion": "success", "status": "completed"}],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "job", "conclusion": "success"}],
        "api_key": "ghp_123456789012345678901234567890123456",
    }
    result = verify_ci_evidence(ci_evidence)
    assert result["valid"] is False
    assert any("Key 'api_key' looks like a secret" in b for b in result["blockers"])


def test_verify_ci_evidence_empty():
    result = verify_ci_evidence({})
    assert result["valid"] is False


@patch("subprocess.run")
def test_verify_ci_evidence_sha_mismatch(mock_run):
    gh_out = {
        "headSha": "badbadbad",
        "conclusion": "success",
        "status": "completed",
        "jobs": [{"name": "job", "conclusion": "success", "status": "completed"}],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "job", "conclusion": "success"}],
    }
    result = verify_ci_evidence(ci_evidence, ["job"])
    assert result["valid"] is False
    assert any("SHA mismatch" in b for b in result["blockers"])


@patch("subprocess.run")
def test_verify_ci_evidence_missing_job(mock_run):
    gh_out = {
        "headSha": "abcdef",
        "conclusion": "success",
        "status": "completed",
        "jobs": [
            {"name": "some-other-job", "conclusion": "success", "status": "completed"}
        ],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "job", "conclusion": "success"}],
    }
    result = verify_ci_evidence(ci_evidence, ["job"])
    assert result["valid"] is False
    assert any("Required job 'job' was not found" in b for b in result["blockers"])


@patch("subprocess.run")
def test_verify_ci_evidence_gh_query_failure(mock_run):
    import subprocess

    mock_run.side_effect = subprocess.CalledProcessError(1, "gh", stderr="Not found")

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "job", "conclusion": "success"}],
    }
    result = verify_ci_evidence(ci_evidence, ["job"])
    assert result["valid"] is False
    assert any("GitHub CLI query failed" in b for b in result["blockers"])


@patch("subprocess.run")
def test_verify_ci_evidence_cancelled_run(mock_run):
    gh_out = {
        "headSha": "abcdef",
        "conclusion": "cancelled",
        "status": "completed",
        "jobs": [{"name": "job", "conclusion": "cancelled", "status": "completed"}],
    }
    m = MagicMock()
    m.stdout = json.dumps(gh_out)
    mock_run.return_value = m

    ci_evidence = {
        "run_id": "12345",
        "run_url": "https://github.com/...",
        "head_sha": "abcdef",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [
            {"name": "job", "conclusion": "success"}
        ],  # provider says success, diff truth
    }
    result = verify_ci_evidence(ci_evidence, ["job"])
    assert result["valid"] is False
    assert any(
        "GitHub run 12345 conclusion is not success" in b for b in result["blockers"]
    )
