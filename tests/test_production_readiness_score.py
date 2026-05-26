import json

from scripts.production_readiness_score import score_readiness


def get_valid_traceability():
    return {f"req_{i}": f"tests/test_{i}.py" for i in range(1, 10)}


def test_missing_adr_013():
    input_data = {
        "adrs": ["ADR-001"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": get_valid_traceability(),
        "signoff_evidence": ".tmp/production-readiness/latest.json",
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Missing ADR-013 from review input." in result["blockers"]


def test_docs_only():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": False, "validation": False},
        "traceability": get_valid_traceability(),
        "signoff_evidence": ".tmp/production-readiness/latest.json",
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Rejected docs-only readiness scoring." in result["blockers"]


def test_valid_minimal_evidence():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": get_valid_traceability(),
        "signoff_evidence": ".tmp/production-readiness/latest.json",
        "green_streak_count": 3,
    }
    result = score_readiness(input_data)
    assert result["ready"]
    assert len(result["blockers"]) == 0
    assert result["score_inputs"]["adrs_present"] == 1
    assert result["score_inputs"]["docs"] is True


def test_green_streak_count_insufficient():
    for count in [0, 1, 2]:
        input_data = {
            "adrs": ["ADR-013"],
            "evidence": {"docs": True, "implementation": True, "validation": True},
            "traceability": get_valid_traceability(),
            "signoff_evidence": ".tmp/production-readiness/latest.json",
            "green_streak_count": count,
        }
        result = score_readiness(input_data)
        assert not result["ready"]
        assert (
            "Production gate requires 3 consecutive clean signoff runs."
            in result["blockers"]
        )


def test_green_streak_count_sufficient():
    for count in [3, 4, 10]:
        input_data = {
            "adrs": ["ADR-013"],
            "evidence": {"docs": True, "implementation": True, "validation": True},
            "traceability": get_valid_traceability(),
            "signoff_evidence": ".tmp/production-readiness/latest.json",
            "green_streak_count": count,
        }
        result = score_readiness(input_data)
        assert result["ready"]
        assert len(result["blockers"]) == 0


def test_missing_implementation_and_validation():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": False, "implementation": False, "validation": False},
        "traceability": get_valid_traceability(),
        "signoff_evidence": ".tmp/production-readiness/latest.json",
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Missing implementation evidence." in result["blockers"]
    assert "Missing validation evidence." in result["blockers"]


def test_traceability_evidence_gap():
    traceability = get_valid_traceability()
    traceability["req_5"] = "Evidence gap"
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": traceability,
        "signoff_evidence": ".tmp/production-readiness/latest.json",
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Traceability row req_5 still says Evidence gap." in result["blockers"]


def test_missing_signoff_evidence():
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": get_valid_traceability(),
        # Missing signoff_evidence
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert "Missing signoff evidence pointer/verifier output." in result["blockers"]


def test_missing_traceability():
    traceability = get_valid_traceability()
    del traceability["req_9"]
    input_data = {
        "adrs": ["ADR-013"],
        "evidence": {"docs": True, "implementation": True, "validation": True},
        "traceability": traceability,
        "signoff_evidence": ".tmp/production-readiness/latest.json",
    }
    result = score_readiness(input_data)
    assert not result["ready"]
    assert (
        "Missing one or more of the 9 blocking requirements evidence."
        in result["blockers"]
    )


def test_strict_rejects_manual_green_streak():
    data = {
        "adrs": ["ADR-013"],
        "evidence": {"implementation": True, "validation": True},
        "traceability": {
            "1": "passed",
            "2": "passed",
            "3": "passed",
            "4": "passed",
            "5": "passed",
            "6": "passed",
            "7": "passed",
            "8": "passed",
            "9": "passed",
        },
        "signoff_evidence": "yes",
        "green_streak_count": 3,
    }
    result = score_readiness(data, strict=True)
    assert not result["ready"]
    assert any(
        "Authoritative readiness requires computed GitHub streak evidence" in b
        for b in result["blockers"]
    )
