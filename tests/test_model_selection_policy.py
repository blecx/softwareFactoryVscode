import json
from pathlib import Path

import pytest

from factory_runtime.agents.model_selection_policy import ModelSelectionPolicy


@pytest.fixture
def temp_profiles_file(tmp_path: Path) -> str:
    profiles = {
        "github-mini": {
            "file_cap": 5,
            "diff_budget": 250,
            "domain_cap": 1,
            "context_class": "narrow",
            "fallback_actions": ["split-issue", "escalate-to-full"],
            "tool_subset": [],
        },
        "github-full": {
            "file_cap": 20,
            "diff_budget": 1000,
            "domain_cap": 3,
            "context_class": "wide",
            "fallback_actions": ["request-human-review", "split-issue"],
            "tool_subset": [],
        },
    }
    p = tmp_path / "profiles.json"
    p.write_text(json.dumps(profiles), encoding="utf-8")
    return str(p)


def test_fits_selected_model(temp_profiles_file: str):
    policy = ModelSelectionPolicy(temp_profiles_file)
    result = policy.evaluate("github-mini", file_count=3, domain_count=1)
    assert result.is_fit is True
    assert result.action_required == "fits-selected-model"


def test_split_issue_required(temp_profiles_file: str):
    policy = ModelSelectionPolicy(temp_profiles_file)
    # Exceeding full profile -> split issue
    result = policy.evaluate("github-full", file_count=25, domain_count=1)
    assert result.is_fit is False
    assert result.action_required == "split-issue-required"


def test_upgrade_model_recommended(temp_profiles_file: str):
    policy = ModelSelectionPolicy(temp_profiles_file)
    # Exceeding mini profile, escalate to full
    result = policy.evaluate("github-mini", file_count=8, domain_count=1)
    assert result.is_fit is False
    assert result.action_required == "upgrade-model-recommended"


def test_blocked_by_authority_contract(temp_profiles_file: str):
    policy = ModelSelectionPolicy(temp_profiles_file)
    result = policy.evaluate(
        "github-mini", file_count=2, domain_count=1, violates_authority=True
    )
    assert result.is_fit is False
    assert result.action_required == "blocked-by-authority-contract"


def test_fallback_when_no_profile_found():
    policy = ModelSelectionPolicy()
    result_fit = policy.evaluate("unknown", file_count=3, domain_count=1)
    assert result_fit.is_fit is True
    assert result_fit.action_required == "fits-selected-model"

    result_split = policy.evaluate("unknown", file_count=6, domain_count=2)
    assert result_split.is_fit is False
    assert result_split.action_required == "split-issue-required"
