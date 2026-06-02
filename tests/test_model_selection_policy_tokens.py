import pytest

from factory_runtime.agents.model_selection_policy import (
    ModelProfile,
    ModelSelectionPolicy,
)


def test_token_budget_blocking_threshold():
    policy = ModelSelectionPolicy()
    policy.profiles["tester"] = ModelProfile(
        name="tester",
        file_cap=5,
        diff_budget=250,
        domain_cap=1,
        context_class="narrow",
        fallback_actions=["split"],
        tool_subset=[],
        prompt_budget=100,
        completion_budget=100,
        context_budget=100,
        warning_threshold=0.8,
        blocking_threshold=1.0,
    )

    # Under limits
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=50, completion_tokens=50, context_tokens=80
    )
    assert res.is_fit is True
    assert "WARNING" not in res.reason

    # Warning for prompt
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=81, completion_tokens=50, context_tokens=80
    )
    assert res.is_fit is True
    assert "WARNING: prompt usage nearing threshold" in res.reason

    # Warning for completion
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=50, completion_tokens=85, context_tokens=80
    )
    assert res.is_fit is True
    assert "WARNING: completion usage nearing threshold" in res.reason

    # Warning for context
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=50, completion_tokens=50, context_tokens=90
    )
    assert res.is_fit is True
    assert "WARNING: context usage nearing threshold" in res.reason

    # Blocked by prompt
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=105, completion_tokens=50, context_tokens=80
    )
    assert res.is_fit is False
    assert "Exceeds prompt blocking threshold" in res.reason

    # Blocked by completion
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=50, completion_tokens=105, context_tokens=80
    )
    assert res.is_fit is False
    assert "Exceeds completion blocking threshold" in res.reason

    # Blocked by context
    res = policy.evaluate(
        "tester", 1, 1, prompt_tokens=50, completion_tokens=50, context_tokens=105
    )
    assert res.is_fit is False
    assert "Exceeds context blocking threshold" in res.reason


def test_fallback_limits():
    policy = ModelSelectionPolicy()

    # Over fallback prompt
    res = policy.evaluate("unknown", 1, 1, prompt_tokens=5000)
    assert res.is_fit is False
    assert "Exceeds fallback token budget limits" in res.reason

    res = policy.evaluate("unknown", 1, 1, completion_tokens=2000)
    assert res.is_fit is False
    assert "Exceeds fallback token budget limits" in res.reason

    res = policy.evaluate("unknown", 1, 1, context_tokens=9000)
    assert res.is_fit is False
    assert "Exceeds fallback token budget limits" in res.reason
