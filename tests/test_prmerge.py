import json
import os
import subprocess
import time

import pytest


@pytest.fixture
def repo_root(tmp_path):
    return str(tmp_path)


@pytest.fixture
def setup_prmerge_env(repo_root, monkeypatch):
    monkeypatch.chdir(repo_root)
    os.makedirs(".tmp", exist_ok=True)

    # We need PYTHONPATH to point to real repo root so it can find "scripts.workflow_preflight_gate"
    real_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    monkeypatch.setenv("PYTHONPATH", real_repo_root)


def test_prmerge_fails_without_preflight(setup_prmerge_env, repo_root):
    # Ensure validation-receipt exists so we only fail on preflight
    with open(".tmp/validation-receipt.json", "w") as f:
        f.write("{}")

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )

    # Run the script
    result = subprocess.run(
        [script_path], cwd=repo_root, capture_output=True, text=True
    )

    assert result.returncode == 1
    assert "Preflight gate failed" in result.stderr
    assert "Missing preflight evidence" in result.stderr


def test_prmerge_fails_on_stale_preflight(setup_prmerge_env, repo_root):
    with open(".tmp/validation-receipt.json", "w") as f:
        f.write("{}")

    path = ".tmp/workflow_preflight_issue-workflow.json"
    evidence = {
        "evidence_key": "issue-workflow",
        "agent": "copilot-workspace",
        "status": "passed",
        "timestamp": time.time() - 1000,  # Stale
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f)

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    result = subprocess.run(
        [script_path], cwd=repo_root, capture_output=True, text=True
    )

    assert result.returncode == 1
    assert "Preflight gate failed" in result.stderr
    assert "Stale preflight evidence" in result.stderr


def test_prmerge_fails_on_failed_preflight(setup_prmerge_env, repo_root):
    with open(".tmp/validation-receipt.json", "w") as f:
        f.write("{}")

    path = ".tmp/workflow_preflight_issue-workflow.json"
    evidence = {
        "evidence_key": "issue-workflow",
        "agent": "copilot-workspace",
        "status": "failed",
        "timestamp": time.time(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f)

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    result = subprocess.run(
        [script_path], cwd=repo_root, capture_output=True, text=True
    )

    assert result.returncode == 1
    assert "Preflight gate failed" in result.stderr
    assert "expected 'passed'" in result.stderr


def test_prmerge_fails_on_exact_state_mismatch(setup_prmerge_env, repo_root):
    from scripts.workflow_preflight_gate import record_preflight_evidence

    # Preflight evidence for WRONG branch
    record_preflight_evidence(
        "issue-workflow",
        "copilot-workspace",
        "passed",
        repo_root,
        branch="wrong-branch",
    )

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    result = subprocess.run(
        [script_path], cwd=repo_root, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Exact state validation failed" in result.stderr
