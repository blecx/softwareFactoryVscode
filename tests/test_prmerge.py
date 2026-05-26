import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone

import pytest


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
        "identity": "copilot-workspace",
        "verdict": "pass",
        "timestamp": (datetime.now(timezone.utc) - timedelta(seconds=1000)).isoformat(),
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
        "identity": "copilot-workspace",
        "verdict": "fail",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    assert "expected 'pass'" in result.stderr


def test_prmerge_fails_on_exact_state_mismatch(setup_prmerge_env, repo_root):
    from scripts.workflow_preflight_gate import record_preflight_evidence

    # Preflight evidence for WRONG branch
    record_preflight_evidence(
        "issue-workflow",
        "copilot-workspace",
        "pass",
        repo_root,
        exact_state={"branch": "wrong-branch"},
    )

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    result = subprocess.run(
        [script_path], cwd=repo_root, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "Exact state validation failed" in result.stderr


def test_prmerge_force_bypass_fails_without_evidence(setup_prmerge_env, repo_root):
    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    result = subprocess.run(
        [script_path, "--force-bypass"], cwd=repo_root, capture_output=True, text=True
    )
    assert result.returncode == 1
    assert (
        "Hard-gate bypass failed" in result.stderr
        or "Missing preflight evidence" in result.stderr
    )


def test_prmerge_force_bypass_passes_with_evidence(
    setup_prmerge_env, repo_root, monkeypatch
):
    import subprocess
    import time

    from scripts.workflow_preflight_gate import record_preflight_evidence

    curr_branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True
    ).stdout.strip()
    record_preflight_evidence(
        "force-bypass",
        "human-operator",
        "pass",
        repo_root,
        exact_state={
            "branch": curr_branch,
            "break_glass": True,
            "bypass_evidence": "Emergency break-glass",
        },
    )

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "scripts", "prmerge")
    )
    # We replace gh in path with a dummy script or let it fail gracefully just because
    # github actions aren't available but prmerge runs `gh pr merge` at the end
    # Actually setup_prmerge_env already mocks gh!
    os.makedirs(os.path.join(repo_root, "bin"), exist_ok=True)
    with open(os.path.join(repo_root, "bin", "gh"), "w") as f:
        f.write("#!/bin/bash\nexit 0\n")
    os.chmod(os.path.join(repo_root, "bin", "gh"), 0o755)
    env = os.environ.copy()
    env["PATH"] = os.path.join(repo_root, "bin") + ":" + env.get("PATH", "")
    result = subprocess.run(
        [script_path, "--force-bypass"],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Bypass authorized." in result.stdout
