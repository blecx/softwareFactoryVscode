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
from factory_runtime.agents.tooling.quota_governance import RequesterClass

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


def _normalize_requester_class(
    requester_class: RequesterClass | str | None,
    *,
    run_id: str | None = None,
    parent_run_id: str | None = None,
) -> str:
    candidate = str(requester_class or "").strip().lower()
    if candidate:
        try:
            return RequesterClass(candidate).value
        except ValueError:
            pass

    if parent_run_id:
        return RequesterClass.SUBAGENT.value
    if run_id:
        return RequesterClass.PARENT_RUN.value
    return RequesterClass.INTERACTIVE.value


def _build_lineage_id(
    requester_class: str,
    *,
    run_id: str | None = None,
    parent_run_id: str | None = None,
) -> str:
    normalized_run_id = (run_id or "").strip()
    normalized_parent_run_id = (parent_run_id or "").strip()
    if requester_class == RequesterClass.SUBAGENT.value and normalized_parent_run_id:
        return normalized_parent_run_id
    if normalized_run_id:
        return normalized_run_id
    if normalized_parent_run_id:
        return normalized_parent_run_id
    return "workspace"


def _build_feedback_scope(policy: LLMQuotaPolicy, lane: str = "foreground") -> str:
    return f"{_build_lease_scope(policy)}:{_normalize_lane(lane)}"


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
    requester_class: str = RequesterClass.INTERACTIVE.value
    lineage_id: str = "workspace"
    shared_feedback_scope: str | None = None


class QuotaBroker:
    """Owns one brokered admission path for outbound provider requests."""

    def __init__(
        self,
        *,
        role: str,
        lane: str,
        policy: LLMQuotaPolicy,
        requester_class: RequesterClass | str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        requester_id: str | None = None,
    ):
        normalized_role = (role or "coding").strip().lower() or "coding"
        normalized_lane = _normalize_lane(lane)
        self.role = normalized_role
        self.lane = normalized_lane
        self.policy = policy
        self.requester_class = _normalize_requester_class(
            requester_class,
            run_id=run_id,
            parent_run_id=parent_run_id,
        )
        self.run_id = (run_id or "").strip() or None
        self.parent_run_id = (parent_run_id or "").strip() or None
        self.lineage_id = _build_lineage_id(
            self.requester_class,
            run_id=self.run_id,
            parent_run_id=self.parent_run_id,
        )
        self.request_channel = _build_request_channel(normalized_role, normalized_lane)
        self.lease_scope = _build_lease_scope(policy)
        self.feedback_scope = _build_feedback_scope(policy, normalized_lane)
        normalized_requester_id = (requester_id or "").strip()
        self.requester_id = normalized_requester_id or (
            f"{self.requester_class}:{self.role}:{self.lineage_id}:broker-{id(self)}"
        )
        self._concurrency_poll_seconds = _resolve_concurrency_poll_seconds()

    @classmethod
    def for_role(
        cls,
        role: str,
        *,
        role_config: Mapping[str, object] | None = None,
        lane: str = "foreground",
        requester_class: RequesterClass | str | None = None,
        run_id: str | None = None,
        parent_run_id: str | None = None,
        requester_id: str | None = None,
    ) -> "QuotaBroker":
        return cls(
            role=role,
            lane=lane,
            policy=resolve_role_quota_policy(role, config=role_config),
            requester_class=requester_class,
            run_id=run_id,
            parent_run_id=parent_run_id,
            requester_id=requester_id,
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
            requester_class=self.requester_class,
            lineage_id=self.lineage_id,
            requester_id=self.requester_id,
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
                requester_class=self.requester_class,
                lineage_id=self.lineage_id,
                shared_feedback_scope=self.feedback_scope,
            )

        rate_limit_wait_seconds = api_throttle.reserve_api_slot(
            channel=self.request_channel,
            role=self.role,
            shared_scope=self.feedback_scope,
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
            requester_class=self.requester_class,
            lineage_id=self.lineage_id,
            shared_feedback_scope=self.feedback_scope,
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
            shared_scope=self.feedback_scope,
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
            shared_scope=self.feedback_scope,
            requester_class=self.requester_class,
            lineage_id=self.lineage_id,
        )
