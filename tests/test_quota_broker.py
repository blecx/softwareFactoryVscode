from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from factory_runtime.agents.llm_client import (
    _LLMRequestThrottle,
    _RateLimitedAsyncHTTPClient,
)
from factory_runtime.agents.tooling import api_throttle
from factory_runtime.agents.tooling.llm_quota_policy import LLMQuotaPolicy
from factory_runtime.agents.tooling.quota_broker import QuotaBroker


def _clear_quota_env(monkeypatch) -> None:
    for name in (
        "WORK_ISSUE_QUOTA_CEILING_RPS",
        "WORK_ISSUE_MAX_RPS",
        "WORK_ISSUE_FOREGROUND_SHARE",
        "WORK_ISSUE_RESERVE_SHARE",
        "WORK_ISSUE_RPS_JITTER",
        "WORK_ISSUE_MAX_THROTTLE_WAIT_SECONDS",
        "WORK_ISSUE_RATE_LIMIT_COOLDOWN_SECONDS",
        "WORK_ISSUE_CONCURRENCY_LEASE_LIMIT",
        "WORK_ISSUE_CONCURRENCY_LEASE_TTL_SECONDS",
        "WORK_ISSUE_CONCURRENCY_LEASE_POLL_SECONDS",
        "WORK_ISSUE_QUOTA_ROLE",
        "WORK_ISSUE_API_THROTTLE_STATE_FILE",
        "WORK_ISSUE_API_THROTTLE_LOCK_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_policy(*, concurrency_lease_limit: int = 1) -> LLMQuotaPolicy:
    return LLMQuotaPolicy(
        provider="github",
        model="openai/gpt-4o-mini",
        model_family="openai/gpt-4o-mini",
        quota_bucket="github-openai-mini",
        quota_source="model-family-fallback",
        quota_ceiling_rps=100.0,
        concurrency_lease_limit=concurrency_lease_limit,
        foreground_share=0.70,
        reserve_share=0.30,
        foreground_lane_rps=100.0,
        reserve_lane_rps=100.0,
        jitter_ratio=0.0,
        max_wait_seconds=1.0,
        rate_limit_cooldown_seconds=45.0,
    )


async def _no_sleep(_: float) -> None:
    return None


def test_quota_broker_reserves_and_releases_shared_concurrency_lease(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    state_file = tmp_path / "api-throttle-state.json"
    lock_file = tmp_path / "api-throttle.lock"
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_STATE_FILE", str(state_file))
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_LOCK_FILE", str(lock_file))
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None: 0.0,
    )

    broker = QuotaBroker(role="coding", lane="foreground", policy=_make_policy())

    reservation = asyncio.run(
        broker.reserve_request_admission(
            local_fallback=None,
            sleeper=_no_sleep,
        )
    )

    assert reservation.concurrency_lease is not None
    state = json.loads(state_file.read_text(encoding="utf-8"))
    scope_state = state["concurrency_leases"][broker.lease_scope]
    assert scope_state["active_lease_count"] == 1
    assert len(scope_state["leases"]) == 1

    broker.release_admission(reservation)

    released_state = json.loads(state_file.read_text(encoding="utf-8"))
    released_scope = released_state["concurrency_leases"][broker.lease_scope]
    assert released_scope["active_lease_count"] == 0
    assert released_scope["lease_release_count"] == 1
    assert released_scope["leases"] == {}


def test_second_broker_waits_for_shared_concurrency_lease_until_first_releases(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    state_file = tmp_path / "api-throttle-state.json"
    lock_file = tmp_path / "api-throttle.lock"
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_STATE_FILE", str(state_file))
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_LOCK_FILE", str(lock_file))
    monkeypatch.setenv("WORK_ISSUE_CONCURRENCY_LEASE_POLL_SECONDS", "0.05")
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None: 0.0,
    )

    clock = {"now": 100.0}
    monkeypatch.setattr(api_throttle.time, "time", lambda: clock["now"])

    first_broker = QuotaBroker(role="coding", lane="foreground", policy=_make_policy())
    second_broker = QuotaBroker(role="coding", lane="foreground", policy=_make_policy())

    first_reservation = asyncio.run(
        first_broker.reserve_request_admission(local_fallback=None, sleeper=_no_sleep)
    )
    sleep_calls: list[float] = []

    async def _release_then_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        first_broker.release_admission(first_reservation)
        clock["now"] += seconds

    second_reservation = asyncio.run(
        second_broker.reserve_request_admission(
            local_fallback=None,
            sleeper=_release_then_sleep,
        )
    )

    assert first_reservation.concurrency_lease is not None
    assert second_reservation.concurrency_lease is not None
    assert sleep_calls == [pytest.approx(0.05)]
    assert second_reservation.concurrency_wait_seconds == pytest.approx(0.05)
    assert second_reservation.queue_wait_seconds == pytest.approx(0.05)

    second_broker.release_admission(second_reservation)


def test_rate_limited_http_client_releases_brokered_lease_after_request(
    monkeypatch,
    tmp_path,
) -> None:
    _clear_quota_env(monkeypatch)
    state_file = tmp_path / "api-throttle-state.json"
    lock_file = tmp_path / "api-throttle.lock"
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_STATE_FILE", str(state_file))
    monkeypatch.setenv("WORK_ISSUE_API_THROTTLE_LOCK_FILE", str(lock_file))
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None: 0.0,
    )

    broker = QuotaBroker(role="coding", lane="foreground", policy=_make_policy())

    async def _run_test() -> httpx.Response:
        client = _RateLimitedAsyncHTTPClient(
            throttle=_LLMRequestThrottle(max_rps=100.0, jitter_ratio=0.0),
            broker=broker,
            role="coding",
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
    state = json.loads(state_file.read_text(encoding="utf-8"))
    scope_state = state["concurrency_leases"][broker.lease_scope]
    assert scope_state["active_lease_count"] == 0
    assert scope_state["lease_grant_count"] == 1
    assert scope_state["lease_release_count"] == 1
