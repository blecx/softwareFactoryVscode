import pytest
from scripts.verify_production_signoff import parse_ci_evidence


def test_parse_valid_payload():
    payload = {
        "run_id": "123456",
        "run_url": "https://github.com/org/repo/actions/runs/123456",
        "head_sha": "abcdef123456",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": [{"name": "build", "conclusion": "success"}],
        "artifacts": [{"name": "dist", "url": "https://github.com/..."}],
    }
    model, blockers = parse_ci_evidence(payload)
    assert model is not None
    assert len(blockers) == 0
    assert model.run_id == "123456"
    assert len(model.jobs) == 1
    assert model.jobs[0].name == "build"
    assert len(model.artifacts) == 1


def test_missing_required_fields():
    payload = {
        "run_id": "123456",
        # missing run_url, head_sha, branch, workflow_name, jobs
    }
    model, blockers = parse_ci_evidence(payload)
    assert model is None
    assert any("Missing required field: 'head_sha'" in b for b in blockers)
    assert any("Missing required field: 'jobs'" in b for b in blockers)


def test_malformed_jobs():
    payload = {
        "run_id": "123456",
        "run_url": "https://github.com/",
        "head_sha": "abc",
        "branch": "main",
        "workflow_name": "CI",
        "jobs": ["not a dict"],
    }
    model, blockers = parse_ci_evidence(payload)
    assert model is None
    assert "Job at index 0 is malformed." in blockers
