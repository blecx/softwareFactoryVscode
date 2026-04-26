"""Brokered quota-governance admission control for outbound provider requests.

This module adds an explicit quota-broker surface on top of the immediate shared
throttle baseline. The broker owns provider-facing request admission and shared
concurrency leasing without becoming a second runtime-truth authority.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping

from factory_runtime.agents.tooling import api_throttle
from factory_runtime.agents.tooling.llm_quota_policy import (
    LLMQuotaPolicy,
    resolve_role_quota_policy,
)

_DEFAULT_CONCURRENCY_LEASE_POLL_SECONDS = 0.05


def _normalize_lane(lane: str) -> str:
    normalized = (lane or "foreground").strip().lower()
    return "reserve" if normalized == "reserve" else "foreground"


def _build_request_channel(role: str, lane: str = "foreground") -> str:
    normalized_role = (role or "coding").strip().lower() or "coding"
    channel = f"llm:{normalized_role}"
    if _normalize_lane(lane) == "reserve":
        return f"{channel}.reserve"
    return channel


def _build_lease_scope(policy: LLMQuotaPolicy) -> str:
    provider = (policy.provider or "unknown").strip().lower() or "unknown"
    quota_bucket = (policy.quota_bucket or "unknown").strip().lower() or "unknown"
    model_family = (policy.model_family or "unknown").strip().lower() or "unknown"
    return f"llm:{provider}:{quota_bucket}:{model_family}"


def _resolve_concurrency_poll_seconds() -> float:
    raw = (os.environ.get("WORK_ISSUE_CONCURRENCY_LEASE_POLL_SECONDS") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = _DEFAULT_CONCURRENCY_LEASE_POLL_SECONDS
    return max(0.01, value)


@dataclass(frozen=True, slots=True)
class ConcurrencyLease:
    """One granted shared concurrency lease."""

    lease_scope: str
    lease_id: str
    lease_limit: int


@dataclass(frozen=True, slots=True)
class AdmissionReservation:
    """Reserved provider-facing request admission state for one outbound call."""

    queue_wait_seconds: float
    rate_limit_wait_seconds: float
    concurrency_wait_seconds: float
    concurrency_lease: ConcurrencyLease | None = None


class QuotaBroker:
    """Owns one brokered admission path for outbound provider requests."""

    def __init__(
        self,
        *,
        role: str,
        lane: str,
        policy: LLMQuotaPolicy,
    ):
        normalized_role = (role or "coding").strip().lower() or "coding"
        normalized_lane = _normalize_lane(lane)
        self.role = normalized_role
        self.lane = normalized_lane
        self.policy = policy
        self.request_channel = _build_request_channel(normalized_role, normalized_lane)
        self.lease_scope = _build_lease_scope(policy)
        self._concurrency_poll_seconds = _resolve_concurrency_poll_seconds()

    @classmethod
    def for_role(
        cls,
        role: str,
        *,
        role_config: Mapping[str, object] | None = None,
        lane: str = "foreground",
    ) -> "QuotaBroker":
        return cls(
            role=role,
            lane=lane,
            policy=resolve_role_quota_policy(role, config=role_config),
        )

    def _try_reserve_concurrency_lease(
        self,
    ) -> tuple[ConcurrencyLease | None, float]:
        lease_limit = max(0, int(self.policy.concurrency_lease_limit))
        if lease_limit <= 0 or not api_throttle.shared_throttle_supported():
            return None, 0.0

        lease_id, wait_seconds = api_throttle.reserve_concurrency_lease(
            lease_scope=self.lease_scope,
            role=self.role,
            limit=lease_limit,
            holder=f"{self.request_channel}:pid-{os.getpid()}",
        )
        if lease_id:
            return (
                ConcurrencyLease(
                    lease_scope=self.lease_scope,
                    lease_id=lease_id,
                    lease_limit=lease_limit,
                ),
                0.0,
            )
        return None, max(wait_seconds, self._concurrency_poll_seconds)

    async def reserve_request_admission(
        self,
        *,
        local_fallback: Callable[[], Awaitable[float]] | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> AdmissionReservation:
        if not api_throttle.shared_throttle_supported():
            fallback_wait = 0.0
            if local_fallback is not None:
                fallback_wait = await local_fallback()
            return AdmissionReservation(
                queue_wait_seconds=fallback_wait,
                rate_limit_wait_seconds=fallback_wait,
                concurrency_wait_seconds=0.0,
                concurrency_lease=None,
            )

        rate_limit_wait_seconds = api_throttle.reserve_api_slot(
            channel=self.request_channel,
            role=self.role,
        )
        if rate_limit_wait_seconds > 0:
            await sleeper(rate_limit_wait_seconds)

        concurrency_wait_seconds = 0.0
        concurrency_lease, wait_hint = self._try_reserve_concurrency_lease()
        while concurrency_lease is None and self.policy.concurrency_lease_limit > 0:
            if concurrency_wait_seconds >= self.policy.max_wait_seconds:
                raise TimeoutError(
                    "Timed out waiting for a shared concurrency lease from the "
                    f"quota broker for {self.lease_scope}."
                )

            bounded_wait = min(
                max(wait_hint, self._concurrency_poll_seconds),
                max(0.01, self.policy.max_wait_seconds - concurrency_wait_seconds),
            )
            await sleeper(bounded_wait)
            concurrency_wait_seconds += bounded_wait
            concurrency_lease, wait_hint = self._try_reserve_concurrency_lease()

        return AdmissionReservation(
            queue_wait_seconds=rate_limit_wait_seconds + concurrency_wait_seconds,
            rate_limit_wait_seconds=rate_limit_wait_seconds,
            concurrency_wait_seconds=concurrency_wait_seconds,
            concurrency_lease=concurrency_lease,
        )

    def release_admission(self, reservation: AdmissionReservation | None) -> None:
        if reservation is None or reservation.concurrency_lease is None:
            return
        api_throttle.release_concurrency_lease(
            lease_scope=reservation.concurrency_lease.lease_scope,
            lease_id=reservation.concurrency_lease.lease_id,
        )

    def apply_rate_limit_penalty(self, penalty_seconds: float | None = None) -> float:
        return api_throttle.apply_rate_limit_penalty(
            channel=self.request_channel,
            penalty_seconds=penalty_seconds,
            role=self.role,
        )

    def record_request_outcome(
        self,
        *,
        queue_wait_seconds: float,
        upstream_processing_seconds: float,
        status_code: int | None,
        retry_after_seconds: float | None,
    ) -> None:
        api_throttle.record_request_outcome(
            channel=self.request_channel,
            queue_wait_seconds=queue_wait_seconds,
            upstream_processing_seconds=upstream_processing_seconds,
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
        )
