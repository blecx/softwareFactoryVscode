from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from factory_runtime.agents.llm_client import (
    LLMClientFactory,
    _LLMRequestThrottle,
    _RateLimitedAsyncHTTPClient,
)
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
        "WORK_ISSUE_API_THROTTLE_STATE_FILE",
        "WORK_ISSUE_API_THROTTLE_LOCK_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_policy(
    *,
    quota_ceiling_rps: float = 0.50,
    foreground_lane_rps: float = 0.35,
    reserve_lane_rps: float = 0.15,
) -> LLMQuotaPolicy:
    return LLMQuotaPolicy(
        provider="github",
        model="openai/gpt-4o-mini",
        model_family="openai/gpt-4o-mini",
        quota_bucket="github-openai-mini",
        quota_source="model-family-fallback",
        quota_ceiling_rps=quota_ceiling_rps,
        foreground_share=0.70,
        reserve_share=0.30,
        foreground_lane_rps=foreground_lane_rps,
        reserve_lane_rps=reserve_lane_rps,
        jitter_ratio=0.10,
        max_wait_seconds=180.0,
        rate_limit_cooldown_seconds=45.0,
    )


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
    policy = _make_policy()
    monkeypatch.setattr(
        api_throttle,
        "resolve_role_quota_policy",
        lambda role="coding": policy,
    )

    assert api_throttle._resolve_max_rps("llm") == pytest.approx(0.35)
    assert api_throttle._resolve_max_rps("llm.reserve") == pytest.approx(0.15)


def test_rate_limited_http_client_uses_shared_workspace_slot(monkeypatch) -> None:
    _clear_quota_env(monkeypatch)

    slot_calls: list[tuple[str, str | None]] = []
    local_acquires: list[str] = []
    sleep_calls: list[float] = []

    async def _fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    async def _fake_acquire() -> None:
        local_acquires.append("local")

    monkeypatch.setattr(api_throttle, "shared_throttle_supported", lambda: True)
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None: slot_calls.append((channel, role)) or 0.25,
    )

    throttle = _LLMRequestThrottle(max_rps=100.0, jitter_ratio=0.0)
    monkeypatch.setattr(throttle, "acquire", _fake_acquire)

    async def _run_test() -> httpx.Response:
        client = _RateLimitedAsyncHTTPClient(
            throttle=throttle,
            role="coding",
            sleeper=_fake_sleep,
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"ok": True})
            ),
        )

        try:
            return await client.get("https://example.test/models")
        finally:
            await client.aclose()

    response = asyncio.run(_run_test())

    assert response.status_code == 200
    assert slot_calls == [("llm:coding", "coding")]
    assert sleep_calls == [pytest.approx(0.25)]
    assert local_acquires == []


def test_rate_limited_http_client_shares_state_across_new_clients(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setenv(
        "WORK_ISSUE_API_THROTTLE_STATE_FILE",
        str(tmp_path / "api-throttle-state.json"),
    )
    monkeypatch.setenv(
        "WORK_ISSUE_API_THROTTLE_LOCK_FILE",
        str(tmp_path / "api-throttle.lock"),
    )
    monkeypatch.setattr(
        api_throttle,
        "resolve_role_quota_policy",
        lambda role="coding": _make_policy(
            quota_ceiling_rps=3.0,
            foreground_lane_rps=2.0,
            reserve_lane_rps=1.0,
        ),
    )
    monkeypatch.setattr(api_throttle.random, "uniform", lambda start, stop: 0.0)
    monkeypatch.setattr(api_throttle.time, "time", lambda: 100.0)

    first_sleep_calls: list[float] = []
    second_sleep_calls: list[float] = []

    async def _record_first_sleep(seconds: float) -> None:
        first_sleep_calls.append(seconds)

    async def _record_second_sleep(seconds: float) -> None:
        second_sleep_calls.append(seconds)

    async def _run_test() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(200, json={"ok": True})
        )
        first_client = _RateLimitedAsyncHTTPClient(
            throttle=_LLMRequestThrottle(max_rps=100.0, jitter_ratio=0.0),
            role="coding",
            sleeper=_record_first_sleep,
            transport=transport,
        )
        second_client = _RateLimitedAsyncHTTPClient(
            throttle=_LLMRequestThrottle(max_rps=100.0, jitter_ratio=0.0),
            role="coding",
            sleeper=_record_second_sleep,
            transport=transport,
        )

        try:
            first_response = await first_client.get("https://example.test/models")
            second_response = await second_client.get("https://example.test/models")
            return first_response, second_response
        finally:
            await first_client.aclose()
            await second_client.aclose()

    first_response, second_response = asyncio.run(_run_test())

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert first_sleep_calls == []
    assert second_sleep_calls == [pytest.approx(0.5)]


def test_rate_limited_http_client_applies_shared_penalty_on_retry_after(
    monkeypatch,
) -> None:
    _clear_quota_env(monkeypatch)

    penalty_calls: list[tuple[str, float | None, str | None]] = []
    monkeypatch.setattr(api_throttle, "shared_throttle_supported", lambda: True)
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None: 0.0,
    )
    monkeypatch.setattr(
        api_throttle,
        "apply_rate_limit_penalty",
        lambda channel="llm", penalty_seconds=None, role=None: penalty_calls.append(
            (channel, penalty_seconds, role)
        )
        or float(penalty_seconds or 0.0),
    )

    async def _run_test() -> httpx.Response:
        client = _RateLimitedAsyncHTTPClient(
            throttle=_LLMRequestThrottle(max_rps=100.0, jitter_ratio=0.0),
            role="coding",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    429,
                    headers={"Retry-After": "7"},
                    text="rate limit",
                )
            ),
        )

        try:
            return await client.get("https://example.test/models")
        finally:
            await client.aclose()

    response = asyncio.run(_run_test())

    assert response.status_code == 429
    assert penalty_calls == [("llm:coding", 7.0, "coding")]


def test_api_throttle_diagnostics_capture_queue_wait_retry_and_cooldown(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setenv(
        "WORK_ISSUE_API_THROTTLE_STATE_FILE",
        str(tmp_path / "api-throttle-state.json"),
    )
    monkeypatch.setenv(
        "WORK_ISSUE_API_THROTTLE_LOCK_FILE",
        str(tmp_path / "api-throttle.lock"),
    )
    monkeypatch.setattr(api_throttle.time, "time", lambda: 250.0)

    api_throttle.record_request_outcome(
        channel="llm:coding",
        queue_wait_seconds=0.5,
        upstream_processing_seconds=1.25,
        status_code=429,
        retry_after_seconds=7.0,
    )
    api_throttle.apply_rate_limit_penalty(
        channel="llm:coding",
        penalty_seconds=7.0,
        role="coding",
    )

    diagnostics = api_throttle.get_throttle_diagnostics()
    summary = diagnostics["summary"]
    channel = diagnostics["channels"]["llm:coding"]

    assert diagnostics["shared_throttle_supported"] is True
    assert summary["request_count"] == 1
    assert summary["total_queue_wait_seconds"] == pytest.approx(0.5)
    assert summary["total_upstream_processing_seconds"] == pytest.approx(1.25)
    assert summary["retry_after_event_count"] == 1
    assert summary["total_retry_after_seconds"] == pytest.approx(7.0)
    assert summary["cooldown_event_count"] == 1
    assert summary["total_cooldown_seconds"] == pytest.approx(7.0)
    assert summary["time_breakdown_seconds"] == {
        "queue_wait": pytest.approx(0.5),
        "upstream_processing": pytest.approx(1.25),
        "retry_after": pytest.approx(7.0),
        "cooldown": pytest.approx(7.0),
    }
    assert channel["last_status_code"] == 429
    assert channel["rate_limit_response_count"] == 1


def test_immediate_policy_throughput_improves_over_legacy_defaults(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setattr(api_throttle.random, "uniform", lambda start, stop: 0.0)
    monkeypatch.setattr(api_throttle.time, "time", lambda: 100.0)

    def _simulate_burst(policy: LLMQuotaPolicy, prefix: str) -> dict:
        state_file = tmp_path / f"{prefix}-state.json"
        lock_file = tmp_path / f"{prefix}.lock"
        monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_STATE_FILE", str(state_file))
        monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_LOCK_FILE", str(lock_file))
        monkeypatch.setattr(
            api_throttle,
            "resolve_role_quota_policy",
            lambda role="coding": policy,
        )
        for _ in range(3):
            wait_seconds = api_throttle.reserve_api_slot("llm:coding", role="coding")
            api_throttle.record_request_outcome(
                channel="llm:coding",
                queue_wait_seconds=wait_seconds,
                upstream_processing_seconds=0.05,
                status_code=200,
            )
        return api_throttle.get_throttle_diagnostics()

    immediate = _simulate_burst(_make_policy(), "immediate")
    legacy = _simulate_burst(
        _make_policy(
            quota_ceiling_rps=0.042857,
            foreground_lane_rps=0.03,
            reserve_lane_rps=0.012857,
        ),
        "legacy",
    )

    assert immediate["summary"]["request_count"] == 3
    assert legacy["summary"]["request_count"] == 3
    assert (
        immediate["summary"]["total_queue_wait_seconds"]
        < legacy["summary"]["total_queue_wait_seconds"]
    )
    assert immediate["summary"]["retry_after_event_count"] == 0
    assert immediate["summary"]["cooldown_event_count"] == 0
    assert legacy["summary"]["retry_after_event_count"] == 0
    assert legacy["summary"]["cooldown_event_count"] == 0


def test_startup_report_exposes_request_quota_policy(monkeypatch) -> None:
    _clear_quota_env(monkeypatch)
    monkeypatch.setattr(
        api_throttle,
        "get_throttle_diagnostics",
        lambda channel_prefix="llm:": {
            "shared_throttle_supported": True,
            "state_path": ".copilot/softwareFactoryVscode/.tmp/api-throttle-state.json",
            "lock_path": ".copilot/softwareFactoryVscode/.tmp/api-throttle.lock",
            "summary": {
                "request_count": 2,
                "queue_wait_event_count": 1,
                "total_queue_wait_seconds": 0.5,
                "avg_queue_wait_seconds": 0.25,
                "max_queue_wait_seconds": 0.5,
                "total_upstream_processing_seconds": 1.5,
                "avg_upstream_processing_seconds": 0.75,
                "retry_after_event_count": 1,
                "total_retry_after_seconds": 7.0,
                "cooldown_event_count": 1,
                "total_cooldown_seconds": 7.0,
                "rate_limit_response_count": 1,
                "time_breakdown_seconds": {
                    "queue_wait": 0.5,
                    "upstream_processing": 1.5,
                    "retry_after": 7.0,
                    "cooldown": 7.0,
                },
            },
            "channels": {
                "llm:coding": {
                    "request_count": 2,
                    "queue_wait_event_count": 1,
                    "total_queue_wait_seconds": 0.5,
                    "avg_queue_wait_seconds": 0.25,
                    "max_queue_wait_seconds": 0.5,
                    "last_queue_wait_seconds": 0.5,
                    "total_upstream_processing_seconds": 1.5,
                    "avg_upstream_processing_seconds": 0.75,
                    "last_upstream_processing_seconds": 1.0,
                    "retry_after_event_count": 1,
                    "total_retry_after_seconds": 7.0,
                    "last_retry_after_seconds": 7.0,
                    "cooldown_event_count": 1,
                    "total_cooldown_seconds": 7.0,
                    "last_cooldown_seconds": 7.0,
                    "rate_limit_response_count": 1,
                    "last_status_code": 429,
                    "next_allowed_ts": 0.0,
                    "updated_at": 0.0,
                    "last_request_finished_at": 0.0,
                }
            },
        },
    )
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
    assert report["request_diagnostics"]["summary"]["request_count"] == 2
    assert report["request_diagnostics"]["summary"]["time_breakdown_seconds"] == {
        "queue_wait": pytest.approx(0.5),
        "upstream_processing": pytest.approx(1.5),
        "retry_after": pytest.approx(7.0),
        "cooldown": pytest.approx(7.0),
    }
    assert (
        report["role_request_policies"]["planning"]["quota_bucket"]
        == "github-openai-standard"
    )
