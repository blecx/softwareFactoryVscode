"""
Aggregate fast test target that proves language authority,
fail-closed routing, signoff evidence scoring, and residue detection
all participate in the >90 percent gate.

This serves as the final readiness aggregate above-90 guardrail bundle.
"""

import subprocess
import sys

import pytest


@pytest.mark.above_90_readiness
def test_aggregate_above_90_readiness_bundle():
    """
    Executes the above-90 aggregate bundle to prove language authority,
    fail-closed routing, signoff evidence scoring, and residue detection.
    """
    test_files = [
        "tests/test_workflow_language_contract.py",
        "tests/test_ai_authority_routing.py",  # Routing proxy
        "tests/test_production_readiness_score.py",  # Signoff evidence
        "tests/test_verify_production_signoff.py",  # Signoff evidence, cancelled-run classification array, durable signoff pointer
        "tests/test_github_ci_evidence.py",  # GitHub evidence verification fixtures
        "tests/test_green_streak.py",  # computed streak
        "tests/test_production_readiness_evidence.py",
        "tests/test_workflow_preflight.py",  # fail-closed preflight
        "tests/test_workflow_residue_check.py",  # Residue detection
    ]

    result = subprocess.run(
        [sys.executable, "-m", "pytest"] + test_files, capture_output=True, text=True
    )

    assert (
        result.returncode == 0
    ), f"Above-90 readiness bundle failed:\n{result.stdout}\n{result.stderr}"
    assert "passed" in result.stdout
