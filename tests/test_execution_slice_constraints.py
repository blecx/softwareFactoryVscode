import pytest

from scripts.validate_execution_slice import validate_slice


def test_pass_validator():
    data = {
        "target_files": ["file1.py", "file2.py"],
        "conceptual_domains": ["slice validation"],
        "diff_size_budget_lines": 150,
    }
    assert validate_slice(data) == "pass"


def test_soft_over_budget_validator_files():
    data = {
        "target_files": ["file1.py", "file2.py", "file3.py", "file4.py"],
        "conceptual_domains": ["slice validation"],
        "diff_size_budget_lines": 150,
    }
    assert validate_slice(data) == "soft-over-budget"


def test_soft_over_budget_validator_diff():
    data = {
        "target_files": ["file1.py"],
        "conceptual_domains": ["slice validation"],
        "diff_size_budget_lines": 350,
    }
    assert validate_slice(data) == "soft-over-budget"


def test_hard_blocked_validator_files():
    data = {
        "target_files": [
            "file1.py",
            "file2.py",
            "file3.py",
            "file4.py",
            "file5.py",
            "file6.py",
        ],
        "conceptual_domains": ["slice validation"],
        "diff_size_budget_lines": 150,
    }
    assert validate_slice(data) == "hard-blocked"


def test_hard_blocked_validator_domains():
    data = {
        "target_files": ["file1.py"],
        "conceptual_domains": ["slice validation", "another domain"],
        "diff_size_budget_lines": 150,
    }
    assert validate_slice(data) == "hard-blocked"


def test_hard_blocked_missing_required():
    data = {"target_files": ["file1.py"]}
    assert validate_slice(data) == "hard-blocked"
