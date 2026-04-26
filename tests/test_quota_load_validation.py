from __future__ import annotations

import asyncio

import pytest

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
        "WORK_ISSUE_CONCURRENCY_WAITER_TTL_SECONDS",
        "WORK_ISSUE_QUOTA_ROLE",
        "WORK_ISSUE_API_THROTTLE_STATE_FILE",
        "WORK_ISSUE_API_THROTTLE_LOCK_FILE",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_policy(*, concurrency_lease_limit: int = 2) -> LLMQuotaPolicy:
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


def test_lease_diagnostics_expose_queue_depth_denials_and_saturation(
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
        "reserve_api_slot",
        lambda channel="llm", role=None, shared_scope=None: 0.0,
    )

    clock = {"now": 100.0}
    monkeypatch.setattr(api_throttle.time, "time", lambda: clock["now"])

    policy = _make_policy(concurrency_lease_limit=1)
    active_broker = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="parent-run",
        run_id="run-active",
    )
    waiting_parent = QuotaBroker(
        role="coding",
        lane="foreground",
        policy=policy,
        requester_class="parent-run",
        run_id="run-waiting",
    )
    waiting_background = QuotaBroker(
        role="coding",
        lane="reserve",
        policy=policy,
        requester_class="background",
        run_id="bg-1",
    )

    active_lease, _ = active_broker._try_reserve_concurrency_lease()
    assert active_lease is not None
    blocked_parent, blocked_parent_wait = (
        waiting_parent._try_reserve_concurrency_lease()
    )
    blocked_background, blocked_background_wait = (
        waiting_background._try_reserve_concurrency_lease()
    )
    assert blocked_parent is None
    assert blocked_background is None
    assert blocked_parent_wait == pytest.approx(0.05)
    assert blocked_background_wait == pytest.approx(0.05)

    clock["now"] += 0.5
    diagnostics = api_throttle.get_throttle_diagnostics()
    summary = diagnostics["summary"]
    lease_scope = diagnostics["concurrency_leases"][active_broker.lease_scope]

    assert lease_scope["lease_limit"] == 1
    assert lease_scope["active_lease_count"] == 1
    assert lease_scope["waiter_count"] == 2
    assert lease_scope["max_waiter_count"] == 2
    assert lease_scope["lease_denial_count"] == 2
    assert lease_scope["saturation_event_count"] == 2
    assert lease_scope["saturated"] is True
    assert lease_scope["saturation_ratio"] == pytest.approx(1.0)
    assert lease_scope["oldest_waiter_seconds"] == pytest.approx(0.5)
    assert summary["lease_denial_count"] == 2
    assert summary["saturated_lease_scope_count"] == 1
    assert summary["max_waiter_count"] == 2
    assert summary["oldest_waiter_seconds_max"] == pytest.approx(0.5)

    assert api_throttle.release_concurrency_lease(
        active_broker.lease_scope,
        active_lease.lease_id,
    )


def test_many_requester_contention_records_repeatable_load_evidence(
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
    monkeypatch.setenv("WORK_ISSUE_CONCURRENCY_LEASE_POLL_SECONDS", "0.005")
    monkeypatch.setattr(
        api_throttle,
        "reserve_api_slot",
        lambda channel="llm", role=None, shared_scope=None: 0.0,
    )

    policy = _make_policy(concurrency_lease_limit=2)
    brokers = [
        QuotaBroker(
            role="coding",
            lane="foreground",
            policy=policy,
            requester_class="interactive",
        ),
        QuotaBroker(
            role="coding",
            lane="foreground",
            policy=policy,
            requester_class="parent-run",
            run_id="run-a",
        ),
        QuotaBroker(
            role="coding",
            lane="foreground",
            policy=policy,
            requester_class="parent-run",
            run_id="run-b",
        ),
        QuotaBroker(
            role="coding",
            lane="foreground",
            policy=policy,
            requester_class="subagent",
            run_id="child-a-1",
            parent_run_id="run-a",
        ),
        QuotaBroker(
            role="coding",
            lane="foreground",
            policy=policy,
            requester_class="subagent",
            run_id="child-b-1",
            parent_run_id="run-b",
        ),
        QuotaBroker(
            role="coding",
            lane="reserve",
            policy=policy,
            requester_class="background",
            run_id="bg-1",
        ),
    ]

    async def _run_load() -> list[float]:
        start = asyncio.Event()

        async def _worker(broker: QuotaBroker) -> float:
            await start.wait()
            reservation = await broker.reserve_request_admission(
                local_fallback=None,
                sleeper=asyncio.sleep,
            )
            try:
                await asyncio.sleep(0.02)
                broker.record_request_outcome(
                    queue_wait_seconds=reservation.queue_wait_seconds,
                    upstream_processing_seconds=0.02,
                    status_code=200,
                    retry_after_seconds=None,
                )
                return reservation.queue_wait_seconds
            finally:
                broker.release_admission(reservation)

        tasks = [asyncio.create_task(_worker(broker)) for broker in brokers]
        start.set()
        return await asyncio.gather(*tasks)

    waits = asyncio.run(_run_load())
    diagnostics = api_throttle.get_throttle_diagnostics()
    summary = diagnostics["summary"]
    lease_scope = diagnostics["concurrency_leases"][brokers[0].lease_scope]

    assert len(waits) == len(brokers)
    assert max(waits) > 0.0
    assert summary["request_count"] == len(brokers)
    assert summary["total_queue_wait_seconds"] > 0.0
    assert summary["lease_grant_count"] == len(brokers)
    assert summary["saturation_event_count"] > 0
    assert summary["max_waiter_count"] >= 2
    assert lease_scope["max_waiter_count"] >= 2
    assert lease_scope["saturation_event_count"] > 0
    assert lease_scope["lease_denial_count"] > 0
    assert lease_scope["active_lease_count"] == 0
    assert lease_scope["saturated"] is False
