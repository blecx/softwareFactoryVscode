"""
Aggregate fast test target that proves preflight, language, routing,
queue, bypass, and no-op guards together reach the >80 percent target.

This serves as the H9 checkpoint for the harness resistance umbrella.
"""

import subprocess
import sys

import pytest


@pytest.mark.harness_resistance
def test_aggregate_harness_resistance_bundle():
    """
    Executes the 7 core hallucination resistance anchors into one fast bundle.
    This proves that the combined harness guards are intact and passing.
    """
    test_files = [
        "tests/test_workflow_preflight.py",
        "tests/test_workflow_language_contract.py",
        "tests/test_ai_authority_routing.py",
        "tests/test_queue_state_validator.py",
        "tests/test_harness_bypass_guard.py",
        "tests/test_subagent_result_guard.py",
        "tests/test_production_readiness_score.py",
    ]

    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + test_files, capture_output=True, text=True
    )

    assert (
        result.returncode == 0
    ), f"Harness resistance bundle failed:\n{result.stdout}\n{result.stderr}"
    assert "passed" in result.stdout
