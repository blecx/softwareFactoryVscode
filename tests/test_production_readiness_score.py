import json

from scripts.production_readiness_score import score_readiness


def test_missing_adr_013():
    input_data = {
        "adrs": ["ADR-001"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Missing ADR-013 from review input." in result["blockers"]


def test_docs_only():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": False, "validation": False},
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Rejected docs-only readiness scoring." in result["blockers"]


def test_valid_minimal_evidence():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
    }
    result = score_readiness(input_data)
    assert result["ready"]
    assert len(result["blockers"]) == 0
    assert result["score_inputs"]["adrs_present"] == 1
    assert result["score_inputs"]["docs"] is True


def test_missing_implementation_and_validation():
    # If docs is false, then docs_only won't trigger, but implementation/validation blockers should.
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": False, "implementation": False, "validation": False},
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Missing implementation evidence." in result["blockers"]
    assert "Missing validation evidence." in result["blockers"]
