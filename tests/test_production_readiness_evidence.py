import json
import os
import tempfile
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch

import pytest

import scripts.production_readiness_evidence as evidence_module
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
    print(result)
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


@pytest.fixture
def valid_authoritative_ci_evidence() -> Dict[str, Any]:
    return {
        "run_id": "12345",
        "run_url": "https://github.example/runs/12345",
        "head_sha": "abcdef123456",
        "branch": "main",
        "workflow_name": "Software Factory CI",
        "jobs": [{"name": "production-validation", "conclusion": "success"}],
    }


def successful_history(count: int = 3):
    return [
        SimpleNamespace(
            run_id=str(i),
            branch="main",
            head_sha=f"sha-{i}",
            status="completed",
            conclusion="success",
            jobs=[
                SimpleNamespace(
                    name="Python Code Quality (Lint & Format)", conclusion="success"
                ),
                SimpleNamespace(
                    name="Architectural Boundary Tests", conclusion="success"
                ),
                SimpleNamespace(name="PR Template Conformance", conclusion="success"),
                SimpleNamespace(name="Production Docs Contract", conclusion="success"),
                SimpleNamespace(
                    name="Production Docker Build Parity", conclusion="success"
                ),
                SimpleNamespace(name="Production Runtime Proofs", conclusion="success"),
                SimpleNamespace(
                    name="Internal Production Gate — Docker Parity & Recovery Proofs",
                    conclusion="success",
                ),
            ],
        )
        for i in range(count, 0, -1)
    ]


@patch("scripts.production_readiness_evidence.verify_ci_evidence")
def test_aggregate_evidence_ci_evidence_success(
    mock_verify, valid_review_input, valid_ci_evidence
):
    mock_verify.return_value = {"valid": True, "blockers": []}
    result = aggregate_evidence(
        valid_review_input, "non_existent_file.json", ci_evidence=valid_ci_evidence
    )
    print(result)
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


def test_aggregate_evidence_strict_missing_ci(valid_review_input, valid_signoff_file):
    result = aggregate_evidence(
        valid_review_input, valid_signoff_file, strict_verification=True
    )
    assert result["ready"] is False
    assert any(
        "GitHub verification is missing in authoritative mode" in b
        for b in result["blockers"]
    )
    assert result["references"]["authoritative"] is False
    assert result["references"]["mode"] == "strict"


@patch("scripts.production_readiness_evidence.verify_ci_evidence")
def test_aggregate_evidence_strict_with_ci(
    mock_verify, valid_review_input, valid_authoritative_ci_evidence
):
    mock_verify.return_value = {"valid": True, "blockers": []}
    with patch("verify_production_signoff.fetch_github_history") as mock_history:
        mock_history.return_value = successful_history()
        result = aggregate_evidence(
            valid_review_input,
            "non_existent_file.json",
            ci_evidence=valid_authoritative_ci_evidence,
            strict_verification=True,
            repo="owner/repo",
        )
    print(result)
    assert result["ready"] is True
    assert len(result["blockers"]) == 0
    assert result["references"]["authoritative"] is True
    assert result["references"]["mode"] == "strict"


@patch("scripts.production_readiness_evidence.verify_ci_evidence")
def test_aggregate_evidence_strict_passes_repo_to_github_verifier(
    mock_verify, valid_review_input, valid_authoritative_ci_evidence
):
    mock_verify.return_value = {"valid": True, "blockers": []}
    with patch("verify_production_signoff.fetch_github_history") as mock_history:
        mock_history.return_value = successful_history()
        aggregate_evidence(
            valid_review_input,
            "non_existent_file.json",
            ci_evidence=valid_authoritative_ci_evidence,
            strict_verification=True,
            repo="owner/repo",
        )

    mock_verify.assert_called_once_with(
        valid_authoritative_ci_evidence, repo="owner/repo", strict=True
    )


def test_main_passes_repo_to_aggregate(tmp_path, monkeypatch):
    input_path = tmp_path / "input.json"
    ci_path = tmp_path / "ci.json"
    input_path.write_text(json.dumps({"adrs": ["ADR-013"]}))
    ci_path.write_text(json.dumps({"run_id": "12345"}))
    captured = {}

    def fake_aggregate(
        review_input,
        signoff_filepath,
        ci_evidence=None,
        strict_verification=False,
        repo=None,
    ):
        captured["repo"] = repo
        captured["strict_verification"] = strict_verification
        captured["ci_evidence"] = ci_evidence
        return {"ready": True, "blockers": []}

    monkeypatch.setattr(evidence_module, "aggregate_evidence", fake_aggregate)

    evidence_module.main(
        [
            "--input",
            str(input_path),
            "--ci-evidence",
            str(ci_path),
            "--strict-verification",
            "--repo",
            "owner/repo",
        ]
    )

    assert captured["repo"] == "owner/repo"
    assert captured["strict_verification"] is True
    assert captured["ci_evidence"] == {"run_id": "12345"}


@patch("verify_production_signoff.fetch_github_history")
def test_aggregate_evidence_strict_github_fetch_failure(mock_fetch, valid_review_input):
    mock_fetch.side_effect = ValueError("GitHub CLI command failed")

    result = aggregate_evidence(
        review_input=valid_review_input,
        signoff_filepath="dummy.md",
        ci_evidence={"branch": "main", "workflow_name": "Test", "head_sha": "abc1234"},
        repo="test/repo",
        strict_verification=True,
    )

    assert result["ready"] is False
    assert "GitHub CLI command failed" in result["blockers"]
