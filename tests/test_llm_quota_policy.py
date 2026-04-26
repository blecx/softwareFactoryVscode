from __future__ import annotations

from pathlib import Path

import pytest

from factory_runtime.agents.llm_client import LLMClientFactory
from factory_runtime.agents.tooling import api_throttle
from factory_runtime.agents.tooling.llm_quota_policy import (
    LLMQuotaPolicy,
    resolve_quota_policy,
    resolve_role_quota_policy,
)


def _clear_quota_env(monkeypatch) -> None:
    for name in (
        "WORK_ISSUE_QUOTA_CEILING_RPS",
        "WORK_ISSUE_MAX_RPS",
        "WORK_ISSUE_FOREGROUND_SHARE",
        "WORK_ISSUE_RESERVE_SHARE",
        "WORK_ISSUE_RPS_JITTER",
        "WORK_ISSUE_MAX_THROTTLE_WAIT_SECONDS",
        "WORK_ISSUE_RATE_LIMIT_COOLDOWN_SECONDS",
        "WORK_ISSUE_QUOTA_ROLE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_resolve_quota_policy_uses_model_family_bucket_and_7030_split(
    monkeypatch,
) -> None:
    _clear_quota_env(monkeypatch)

    policy = resolve_quota_policy(
        provider="github",
        model="openai/gpt-4o-mini",
        base_url="https://models.github.ai/inference",
    )

    assert policy.quota_bucket == "github-openai-mini"
    assert policy.quota_source == "model-family-fallback"
    assert policy.quota_ceiling_rps == pytest.approx(0.50)
    assert policy.foreground_share == pytest.approx(0.70)
    assert policy.reserve_share == pytest.approx(0.30)
    assert policy.foreground_lane_rps == pytest.approx(0.35)
    assert policy.reserve_lane_rps == pytest.approx(0.15)


def test_resolve_role_quota_policy_changes_bucket_when_role_model_changes(
    monkeypatch,
) -> None:
    _clear_quota_env(monkeypatch)
    config = {
        "provider": "github",
        "roles": {
            "planning": {
                "model": "openai/gpt-4o",
                "base_url": "https://models.github.ai/inference",
            },
            "coding": {
                "model": "openai/gpt-4o-mini",
                "base_url": "https://models.github.ai/inference",
            },
        },
    }

    planning_policy = resolve_role_quota_policy("planning", config=config)
    coding_policy = resolve_role_quota_policy("coding", config=config)

    assert planning_policy.quota_bucket == "github-openai-standard"
    assert coding_policy.quota_bucket == "github-openai-mini"
    assert planning_policy.quota_ceiling_rps < coding_policy.quota_ceiling_rps


def test_resolve_quota_policy_honors_legacy_foreground_override(monkeypatch) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setenv("WORK_ISSUE_MAX_RPS", "0.21")

    policy = resolve_quota_policy(
        provider="github",
        model="openai/gpt-4o",
        base_url="https://models.github.ai/inference",
    )

    assert policy.quota_bucket == "legacy-foreground-override"
    assert policy.quota_source == "WORK_ISSUE_MAX_RPS"
    assert policy.quota_ceiling_rps == pytest.approx(0.30)
    assert policy.foreground_lane_rps == pytest.approx(0.21)
    assert policy.reserve_lane_rps == pytest.approx(0.09)


def test_api_throttle_distinguishes_foreground_and_reserve_lanes(monkeypatch) -> None:
    _clear_quota_env(monkeypatch)
    policy = LLMQuotaPolicy(
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
    monkeypatch.setattr(
        api_throttle,
        "resolve_role_quota_policy",
        lambda role="coding": policy,
    )

    assert api_throttle._resolve_max_rps("llm") == pytest.approx(0.35)
    assert api_throttle._resolve_max_rps("llm.reserve") == pytest.approx(0.15)


def test_startup_report_exposes_request_quota_policy(monkeypatch) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setattr(
        LLMClientFactory,
        "get_config_path",
        staticmethod(lambda: Path("configs/llm.default.json")),
    )
    monkeypatch.setattr(
        LLMClientFactory,
        "load_config",
        staticmethod(
            lambda: {
                "provider": "github",
                "api_base": "https://models.github.ai/inference",
            }
        ),
    )
    monkeypatch.setattr(
        LLMClientFactory,
        "get_model_roles",
        staticmethod(
            lambda: {
                "planning": "openai/gpt-4o",
                "coding": "openai/gpt-4o-mini",
                "review": "openai/gpt-4o-mini",
            }
        ),
    )

    def _role_config(role: str) -> dict[str, str]:
        model = "openai/gpt-4o" if role == "planning" else "openai/gpt-4o-mini"
        return {
            "provider": "github",
            "api_base": "https://models.github.ai/inference",
            "model": model,
        }

    monkeypatch.setattr(
        LLMClientFactory,
        "get_role_config",
        staticmethod(_role_config),
    )

    report = LLMClientFactory.get_startup_report()

    assert report["request_quota_policy"]["quota_bucket"] == "github-openai-mini"
    assert report["request_throttle"]["max_rps"] == pytest.approx(0.35)
    assert (
        report["role_request_policies"]["planning"]["quota_bucket"]
        == "github-openai-standard"
    )
