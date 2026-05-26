import json
import os
import time
from datetime import datetime, timezone

import pytest

from scripts.workflow_preflight_gate import (
    get_evidence_path,
    record_preflight_evidence,
    require_safe_preflight,
    validate_against_schema,
)


@pytest.fixture
def repo_root(tmp_path):
    import shutil

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(os.path.join(tmp_path, "schemas"), exist_ok=True)
    shutil.copy(
        os.path.join(repo, "schemas", "workflow-preflight-evidence.schema.json"),
        os.path.join(tmp_path, "schemas", "workflow-preflight-evidence.schema.json"),
    )
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
    record_preflight_evidence("auth-key", "@test-agent", "pass", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert result["safe_to_continue"]
    assert not result["blockers"]


def test_failed_status_blocks(repo_root):
    record_preflight_evidence("auth-key", "@test-agent", "fail", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("expected 'pass'" in b for b in result["blockers"])


def test_mismatched_agent_blocks(repo_root):
    record_preflight_evidence("auth-key", "@wrong-agent", "pass", repo_root)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("Mismatched identity" in b for b in result["blockers"])


def test_stale_evidence_blocks(repo_root, monkeypatch):
    # Mock time to 10 minutes in the future
    current_time = time.time()

    def mock_time():
        return current_time + 600

    record_preflight_evidence("auth-key", "@test-agent", "pass", repo_root)

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


def test_verify_preflight_evidence_exits_on_failure(repo_root):
    with pytest.raises(SystemExit) as exc_info:
        from scripts.workflow_preflight_gate import verify_preflight_evidence

        verify_preflight_evidence("missing-key", "@test-agent", 300, repo_root)
    assert exc_info.value.code == 1


def test_verify_preflight_evidence_passes(repo_root):
    from scripts.workflow_preflight_gate import (
        record_preflight_evidence,
        verify_preflight_evidence,
    )

    record_preflight_evidence("auth-key", "@test-agent", "pass", repo_root)
    verify_preflight_evidence("auth-key", "@test-agent", 300, repo_root)


def test_exact_state_matching_passes(repo_root):
    record_preflight_evidence(
        "auth-key",
        "@test-agent",
        "pass",
        repo_root,
        exact_state={"issue_number": "533", "branch": "issue-533"},
    )

    result = require_safe_preflight(
        "auth-key",
        "@test-agent",
        300,
        repo_root,
        exact_state={"issue_number": "533", "branch": "issue-533"},
    )
    assert result["safe_to_continue"]
    assert not result["blockers"]


def test_exact_state_missing_blocks(repo_root):
    record_preflight_evidence(
        "auth-key",
        "@test-agent",
        "pass",
        repo_root,
        exact_state={"issue_number": "533"},
    )

    result = require_safe_preflight(
        "auth-key",
        "@test-agent",
        300,
        repo_root,
        exact_state={"issue_number": "533", "branch": "issue-533"},
    )
    assert not result["safe_to_continue"]
    assert any("missing expected field 'branch'" in b for b in result["blockers"])


def test_exact_state_mismatch_blocks(repo_root):
    record_preflight_evidence(
        "auth-key",
        "@test-agent",
        "pass",
        repo_root,
        exact_state={"issue_number": "533", "branch": "main"},
    )

    result = require_safe_preflight(
        "auth-key",
        "@test-agent",
        300,
        repo_root,
        exact_state={"issue_number": "533", "branch": "issue-533"},
    )
    assert not result["safe_to_continue"]
    assert any(
        "Exact state validation failed for 'branch'" in b for b in result["blockers"]
    )


def test_strict_schema_rejects_additional_exact_state_properties(repo_root):
    with pytest.raises(ValueError) as exc_info:
        record_preflight_evidence(
            "auth-key",
            "@test-agent",
            "pass",
            repo_root,
            exact_state={"unknown_field": "123"},
        )

    message = str(exc_info.value)
    assert "Additional" in message
    assert "unknown_field" in message


def test_production_writer_emits_schema_compatible_evidence(repo_root):
    record_preflight_evidence(
        "issue-workflow",
        "copilot-workspace",
        "pass",
        repo_root,
        exact_state={
            "issue_number": "561",
            "branch": "issue-572-recovery",
            "worktree": ".tmp/queue-worktrees/572-recovery",
        },
    )

    path = get_evidence_path("issue-workflow", repo_root)
    with open(path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    valid, blockers = validate_against_schema(evidence, repo_root)
    assert valid, blockers
    assert evidence["identity"] == "copilot-workspace"
    assert evidence["verdict"] == "pass"
    assert evidence["exact_state"]["issue_number"] == "561"


def test_future_dated_evidence_blocks(repo_root):
    path = get_evidence_path("auth-key", repo_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    evidence = {
        "identity": "@test-agent",
        "verdict": "pass",
        "timestamp": datetime.fromtimestamp(
            time.time() + 120, timezone.utc
        ).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f)

    result = require_safe_preflight("auth-key", "@test-agent", 300, repo_root)
    assert not result["safe_to_continue"]
    assert any("future" in b for b in result["blockers"])


def test_step2_backend_evidence_binding(repo_root):
    record_preflight_evidence(
        "step2-backend",
        "copilot-workspace",
        "pass",
        repo_root,
        exact_state={
            "issue_number": "563",
            "branch": "feat/563-step2-preflight",
            "checkpoint": "session-12345",
        },
    )

    path = get_evidence_path("step2-backend", repo_root)
    import json

    with open(path, "r", encoding="utf-8") as f:
        evidence = json.load(f)

    valid, blockers = validate_against_schema(evidence, repo_root)
    assert valid, blockers
    assert evidence["exact_state"]["checkpoint"] == "session-12345"
