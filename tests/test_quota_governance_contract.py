from __future__ import annotations

import pytest

from factory_runtime.agents.tooling.llm_quota_policy import LLMQuotaPolicy
from factory_runtime.agents.tooling.quota_governance import (
    QuotaAuthorityScope,
    QuotaBudgetScope,
    QuotaDimension,
    QuotaLane,
    RequesterClass,
    build_default_quota_governance_contract,
)


def _make_policy() -> LLMQuotaPolicy:
    return LLMQuotaPolicy(
        provider="github",
        model="openai/gpt-4o-mini",
        model_family="openai/gpt-4o-mini",
        quota_bucket="github-openai-mini",
        quota_source="model-family-fallback",
        quota_ceiling_rps=0.50,
        foreground_share=0.70,
        reserve_share=0.30,
        foreground_lane_rps=0.35,
        reserve_lane_rps=0.15,
        jitter_ratio=0.10,
        max_wait_seconds=180.0,
        rate_limit_cooldown_seconds=45.0,
    )


def test_default_quota_governance_contract_defines_authority_and_hierarchy() -> None:
    contract = build_default_quota_governance_contract(_make_policy())

    assert contract.version == "1.0"
    assert contract.authority_boundary.authority_name == "quota-broker"
    assert (
        contract.authority_boundary.authority_scope
        == QuotaAuthorityScope.WORKSPACE_SCOPED
    )
    assert contract.authority_boundary.runtime_truth_owner == "mcp-runtime-manager"
    assert contract.authority_boundary.runtime_readiness_owner == "mcp-runtime-manager"
    assert contract.quota_dimensions == (
        QuotaDimension.REQUESTS_PER_SECOND,
        QuotaDimension.TOKENS_PER_MINUTE,
        QuotaDimension.CONCURRENCY_LEASES,
    )
    assert [level.scope for level in contract.budget_hierarchy] == [
        QuotaBudgetScope.PROVIDER,
        QuotaBudgetScope.MODEL_FAMILY,
        QuotaBudgetScope.WORKSPACE,
        QuotaBudgetScope.RUN,
        QuotaBudgetScope.REQUESTER,
    ]
    assert contract.provider_budget.requests_per_second_ceiling == pytest.approx(0.50)
    assert contract.provider_budget.token_quota_per_minute is None
    assert contract.provider_budget.concurrency_lease_limit is None


def test_subagent_requesters_inherit_parent_run_budget() -> None:
    contract = build_default_quota_governance_contract(_make_policy())

    interactive = contract.get_requester_policy(RequesterClass.INTERACTIVE)
    subagent = contract.get_requester_policy(RequesterClass.SUBAGENT)
    background = contract.get_requester_policy(RequesterClass.BACKGROUND)

    assert interactive.parent_budget_scope == QuotaBudgetScope.WORKSPACE
    assert interactive.default_lane == QuotaLane.FOREGROUND
    assert subagent.parent_budget_scope == QuotaBudgetScope.RUN
    assert subagent.default_lane == QuotaLane.FOREGROUND
    assert subagent.inherits_parent_budget is True
    assert subagent.may_open_independent_provider_budget is False
    assert background.default_lane == QuotaLane.RESERVE


def test_contract_serialization_preserves_lane_split_and_dimensions() -> None:
    contract = build_default_quota_governance_contract(_make_policy())

    payload = contract.as_dict()
    lanes = {entry["lane"]: entry for entry in payload["lane_allocations"]}

    assert payload["quota_dimensions"] == [
        "requests-per-second",
        "tokens-per-minute",
        "concurrency-leases",
    ]
    assert lanes["foreground"]["share"] == pytest.approx(0.70)
    assert lanes["foreground"]["request_rate_rps"] == pytest.approx(0.35)
    assert lanes["reserve"]["share"] == pytest.approx(0.30)
    assert lanes["reserve"]["request_rate_rps"] == pytest.approx(0.15)
    assert lanes["reserve"]["receives_reserved_capacity"] is True
    assert "per-process" in payload["notes"][1]
