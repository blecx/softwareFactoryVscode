import json
import os
import time

import pytest

from scripts.workflow_preflight_gate import (
    get_evidence_path,
    record_preflight_evidence,
    require_safe_preflight,
)


@pytest.fixture
def repo_root(tmp_path):
    return str(tmp_path)


def test_get_evidence_path(repo_root):
    path = get_evidence_path("test-key", repo_root)
    assert os.path.basename(path) == "workflow_preflight_test-key.json"
    assert ".tmp" in path


def test_get_evidence_path_sanitize(repo_root):
    path = get_evidence_path("test/key*", repo_root)
    assert os.path.basename(path) == "workflow_preflight_testkey.json"


def test_missing_evidence(repo_root):
    result = require_safe_preflight("missing-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert "Missing preflight evidence" in result["blockers"][0]


def test_record_and_require_safe_evidence(repo_root):
    record_preflight_evidence("auth-key", "@test-agent", "passed", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert result["safe_to_continue"]
    assert not result["blockers"]


def test_failed_status_blocks(repo_root):
    record_preflight_evidence("auth-key", "@test-agent", "failed", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("expected 'passed'" in b for b in result["blockers"])


def test_mismatched_agent_blocks(repo_root):
    record_preflight_evidence("auth-key", "@wrong-agent", "passed", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("Mismatched agent" in b for b in result["blockers"])


def test_stale_evidence_blocks(repo_root, monkeypatch):
    # Mock time to 10 minutes in the future
    current_time = time.time()

    def mock_time():
        return current_time + 600

    record_preflight_evidence("auth-key", "@test-agent", "passed", repo_root)

    monkeypatch.setattr(time, "time", mock_time)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("Stale preflight evidence" in b for b in result["blockers"])


def test_corrupted_evidence(repo_root):
    path = get_evidence_path("auth-key", repo_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{invalid_json: true")

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("Failed to read preflight evidence" in b for b in result["blockers"])
