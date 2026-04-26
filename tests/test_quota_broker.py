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
        lambda channel="llm", role=None, shared_scope=None: 0.0,
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
        lambda channel="llm", role=None, shared_scope=None: 0.0,
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
        lambda channel="llm", role=None, shared_scope=None: 0.0,
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


def test_subagent_lineage_cannot_open_parallel_child_leases(
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
        lambda channel="llm", role=None, shared_scope=None: 0.0,
    )

    policy = _make_policy(concurrency_lease_limit=2)
    first_subagent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="subagent",
        run_id="child-a",
        parent_run_id="run-123",
    )
    second_subagent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="subagent",
        run_id="child-b",
        parent_run_id="run-123",
    )
    other_lineage_subagent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="subagent",
        run_id="child-c",
        parent_run_id="run-999",
    )

    first_lease, _ = first_subagent._try_reserve_concurrency_lease()
    second_lease, second_wait = second_subagent._try_reserve_concurrency_lease()
    other_lineage_lease, _ = other_lineage_subagent._try_reserve_concurrency_lease()

    assert first_lease is not None
    assert second_lease is None
    assert second_wait == pytest.approx(0.05)
    assert other_lineage_lease is not None

    state = json.loads(state_file.read_text(encoding="utf-8"))
    scope_state = state["concurrency_leases"][first_subagent.lease_scope]
    assert scope_state["subagent_parallelism_cap_hits"] >= 1

    assert api_throttle.release_concurrency_lease(
        first_subagent.lease_scope,
        first_lease.lease_id,
    )
    assert api_throttle.release_concurrency_lease(
        other_lineage_subagent.lease_scope,
        other_lineage_lease.lease_id,
    )


def test_parent_run_waiter_beats_subagent_waiter_after_capacity_returns(
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
        lambda channel="llm", role=None, shared_scope=None: 0.0,
    )

    clock = {"now": 100.0}
    monkeypatch.setattr(api_throttle.time, "time", lambda: clock["now"])

    policy = _make_policy(concurrency_lease_limit=1)
    active_subagent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="subagent",
        run_id="child-active",
        parent_run_id="run-other-a",
    )
    waiting_subagent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="subagent",
        run_id="child-waiting",
        parent_run_id="run-other-b",
    )
    parent_run = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="parent-run",
        run_id="run-123",
    )

    active_lease, _ = active_subagent._try_reserve_concurrency_lease()
    blocked_subagent, blocked_subagent_wait = (
        waiting_subagent._try_reserve_concurrency_lease()
    )
    blocked_parent, blocked_parent_wait = parent_run._try_reserve_concurrency_lease()

    assert active_lease is not None
    assert blocked_subagent is None
    assert blocked_subagent_wait == pytest.approx(0.05)
    assert blocked_parent is None
    assert blocked_parent_wait == pytest.approx(0.05)

    assert api_throttle.release_concurrency_lease(
        active_subagent.lease_scope,
        active_lease.lease_id,
    )
    clock["now"] += 0.05

    still_waiting_subagent, retry_hint = (
        waiting_subagent._try_reserve_concurrency_lease()
    )
    granted_parent, _ = parent_run._try_reserve_concurrency_lease()

    assert still_waiting_subagent is None
    assert retry_hint == pytest.approx(0.05)
    assert granted_parent is not None

    state = json.loads(state_file.read_text(encoding="utf-8"))
    scope_state = state["concurrency_leases"][parent_run.lease_scope]
    assert scope_state["priority_wait_event_count"] >= 1

    assert api_throttle.release_concurrency_lease(
        parent_run.lease_scope,
        granted_parent.lease_id,
    )
