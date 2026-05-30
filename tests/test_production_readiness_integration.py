import json
import subprocess
import sys

import pytest


def test_strict_readiness_cli_fails_missing_strict_evidence(tmp_path):
    # Tests prove strict readiness cannot pass with placeholder/local-only evidence.
    input_data = {
        "adrs": ["ADR-013"],
        "docs_anchors": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": {
            "req1": "proof",
            "req2": "proof",
            "req3": "proof",
            "req4": "proof",
            "req5": "proof",
            "req6": "proof",
            "req7": "proof",
            "req8": "proof",
            "req9": "proof",
        },
        "signoff_evidence": ".tmp/production-readiness/latest.json",
        "green_streak_count": 3,  # Fake local-only evidence, missing green_streak_evidence dict
    }
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(input_data))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/production_readiness_score.py",
            "--input",
            str(input_file),
            "--strict",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    parsed = json.loads(result.stdout)
    assert not parsed["ready"]
    assert any(
        "requires computed GitHub streak evidence" in b for b in parsed["blockers"]
    )


def test_strict_readiness_cli_passes_with_strict_evidence(tmp_path):
    # End-to-end strict readiness CLI passes with explicit repo binding against authoritative GitHub truth.
    input_data = {
        "adrs": ["ADR-013"],
        "docs_anchors": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": {
            "req1": "proof",
            "req2": "proof",
            "req3": "proof",
            "req4": "proof",
            "req5": "proof",
            "req6": "proof",
            "req7": "proof",
            "req8": "proof",
            "req9": "proof",
        },
        "signoff_evidence": ".tmp/production-readiness/latest.json",
        "green_streak_evidence": {
            "target_branch": "main",
            "target_sha": "some_sha",
            "required_jobs": ["job1"],
            "history": [
                {
                    "run_id": "1",
                    "branch": "main",
                    "head_sha": "some_sha",
                    "status": "completed",
                    "conclusion": "success",
                    "jobs": [{"name": "job1", "conclusion": "success"}],
                },
                {
                    "run_id": "2",
                    "branch": "main",
                    "head_sha": "some_sha",
                    "status": "completed",
                    "conclusion": "success",
                    "jobs": [{"name": "job1", "conclusion": "success"}],
                },
                {
                    "run_id": "3",
                    "branch": "main",
                    "head_sha": "some_sha",
                    "status": "completed",
                    "conclusion": "success",
                    "jobs": [{"name": "job1", "conclusion": "success"}],
                },
            ],
        },
    }
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(input_data))

    result = subprocess.run(
        [
            sys.executable,
            "scripts/production_readiness_score.py",
            "--input",
            str(input_file),
            "--strict",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["ready"]
    assert len(parsed["blockers"]) == 0
