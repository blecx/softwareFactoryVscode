import json
import os
import random
import re
import time
import uuid
from pathlib import Path

from factory_runtime.agents.tooling.llm_quota_policy import resolve_role_quota_policy

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


_DEFAULT_CONCURRENCY_LEASE_TTL_SECONDS = 900.0


def _parse_float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _parse_int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _coerce_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round_metric(value: float) -> float:
    return round(max(0.0, float(value)), 6)


def shared_throttle_supported() -> bool:
    return fcntl is not None


def _resolve_role(role: str | None = None) -> str:
    if role is not None:
        value = role.strip().lower()
        if value:
            return value

    value = (os.environ.get("WORK_ISSUE_QUOTA_ROLE") or "coding").strip().lower()
    return value or "coding"


def _resolve_lane(channel: str) -> str:
    normalized = (channel or "llm").strip().lower()
    if (
        normalized == "reserve"
        or normalized.endswith(":reserve")
        or normalized.endswith(".reserve")
    ):
        return "reserve"
    return "foreground"


def _resolve_max_rps(channel: str = "llm", role: str | None = None) -> float:
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    if _resolve_lane(channel) == "reserve":
        return max(0.0, policy.reserve_lane_rps)
    return max(0.0, policy.foreground_lane_rps)


def _resolve_jitter_ratio(role: str | None = None) -> float:
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    return _clamp(policy.jitter_ratio, 0.0, 1.0)


def _resolve_max_wait_seconds(role: str | None = None) -> float:
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    return max(1.0, policy.max_wait_seconds)


def _resolve_rate_limit_cooldown_seconds(role: str | None = None) -> float:
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    return max(1.0, policy.rate_limit_cooldown_seconds)


def _resolve_concurrency_lease_limit(role: str | None = None) -> int:
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    return max(1, int(policy.concurrency_lease_limit))


def _resolve_concurrency_lease_ttl_seconds(role: str | None = None) -> float:
    env_default = _parse_float_env(
        "WORK_ISSUE_CONCURRENCY_LEASE_TTL_SECONDS",
        _DEFAULT_CONCURRENCY_LEASE_TTL_SECONDS,
    )
    policy = resolve_role_quota_policy(role=_resolve_role(role))
    return max(30.0, env_default, policy.max_wait_seconds)


def _state_path() -> Path:
    configured = (os.environ.get("WORK_ISSUE_API_THROTTLE_STATE_FILE") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(".copilot/softwareFactoryVscode/.tmp") / "api-throttle-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _lock_path() -> Path:
    configured = (os.environ.get("WORK_ISSUE_API_THROTTLE_LOCK_FILE") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(".copilot/softwareFactoryVscode/.tmp") / "api-throttle.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(path: Path, state: dict) -> None:
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state), encoding="utf-8")
    temp_path.replace(path)


def _ensure_channel_state(state: dict, channel: str) -> dict:
    channels = state.get("channels")
    if not isinstance(channels, dict):
        channels = {}
        state["channels"] = channels

    channel_state = channels.get(channel)
    if not isinstance(channel_state, dict):
        channel_state = {}
        channels[channel] = channel_state

    return channel_state


def _ensure_lease_scope_state(state: dict, lease_scope: str) -> dict:
    lease_scopes = state.get("concurrency_leases")
    if not isinstance(lease_scopes, dict):
        lease_scopes = {}
        state["concurrency_leases"] = lease_scopes

    scope_state = lease_scopes.get(lease_scope)
    if not isinstance(scope_state, dict):
        scope_state = {}
        lease_scopes[lease_scope] = scope_state

    leases = scope_state.get("leases")
    if not isinstance(leases, dict):
        leases = {}
        scope_state["leases"] = leases

    return scope_state


def _prune_expired_leases(scope_state: dict, now: float) -> None:
    leases = scope_state.get("leases")
    if not isinstance(leases, dict):
        leases = {}
        scope_state["leases"] = leases

    expired = 0
    for lease_id, lease_payload in list(leases.items()):
        if not isinstance(lease_payload, dict):
            leases.pop(lease_id, None)
            expired += 1
            continue

        expires_at = _coerce_float(lease_payload.get("expires_at"), 0.0)
        if expires_at > 0 and expires_at <= now:
            leases.pop(lease_id, None)
            expired += 1

    if expired:
        scope_state["expired_lease_reap_count"] = (
            _coerce_int(scope_state.get("expired_lease_reap_count"), 0) + expired
        )

    scope_state["active_lease_count"] = len(leases)


def _summarize_channel(channel_state: dict) -> dict:
    request_count = max(0, _coerce_int(channel_state.get("request_count"), 0))
    total_queue_wait_seconds = _round_metric(
        _coerce_float(channel_state.get("total_queue_wait_seconds"), 0.0)
    )
    total_upstream_processing_seconds = _round_metric(
        _coerce_float(channel_state.get("total_upstream_processing_seconds"), 0.0)
    )
    total_retry_after_seconds = _round_metric(
        _coerce_float(channel_state.get("total_retry_after_seconds"), 0.0)
    )
    total_cooldown_seconds = _round_metric(
        _coerce_float(channel_state.get("total_cooldown_seconds"), 0.0)
    )
    avg_queue_wait_seconds = (
        _round_metric(total_queue_wait_seconds / request_count)
        if request_count
        else 0.0
    )
    avg_upstream_processing_seconds = (
        _round_metric(total_upstream_processing_seconds / request_count)
        if request_count
        else 0.0
    )

    return {
        "request_count": request_count,
        "queue_wait_event_count": max(
            0, _coerce_int(channel_state.get("queue_wait_event_count"), 0)
        ),
        "total_queue_wait_seconds": total_queue_wait_seconds,
        "avg_queue_wait_seconds": avg_queue_wait_seconds,
        "max_queue_wait_seconds": _round_metric(
            _coerce_float(channel_state.get("max_queue_wait_seconds"), 0.0)
        ),
        "last_queue_wait_seconds": _round_metric(
            _coerce_float(channel_state.get("last_queue_wait_seconds"), 0.0)
        ),
        "total_upstream_processing_seconds": total_upstream_processing_seconds,
        "avg_upstream_processing_seconds": avg_upstream_processing_seconds,
        "last_upstream_processing_seconds": _round_metric(
            _coerce_float(
                channel_state.get("last_upstream_processing_seconds"),
                0.0,
            )
        ),
        "retry_after_event_count": max(
            0, _coerce_int(channel_state.get("retry_after_event_count"), 0)
        ),
        "total_retry_after_seconds": total_retry_after_seconds,
        "last_retry_after_seconds": _round_metric(
            _coerce_float(channel_state.get("last_retry_after_seconds"), 0.0)
        ),
        "cooldown_event_count": max(
            0, _coerce_int(channel_state.get("cooldown_event_count"), 0)
        ),
        "total_cooldown_seconds": total_cooldown_seconds,
        "last_cooldown_seconds": _round_metric(
            _coerce_float(channel_state.get("last_cooldown_seconds"), 0.0)
        ),
        "rate_limit_response_count": max(
            0, _coerce_int(channel_state.get("rate_limit_response_count"), 0)
        ),
        "last_status_code": channel_state.get("last_status_code"),
        "next_allowed_ts": _round_metric(
            _coerce_float(channel_state.get("next_allowed_ts"), 0.0)
        ),
        "updated_at": _round_metric(
            _coerce_float(channel_state.get("updated_at"), 0.0)
        ),
        "last_request_finished_at": _round_metric(
            _coerce_float(channel_state.get("last_request_finished_at"), 0.0)
        ),
    }


def _load_state_snapshot() -> dict:
    state_path = _state_path()
    lock_path = _lock_path()

    if not shared_throttle_supported():
        return _load_state(state_path)

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
        state = _load_state(state_path)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return state


def get_throttle_diagnostics(channel_prefix: str = "llm:") -> dict:
    state = _load_state_snapshot()
    channels = state.get("channels")
    if not isinstance(channels, dict):
        channels = {}

    selected_channels = {
        name: value
        for name, value in channels.items()
        if isinstance(name, str)
        and isinstance(value, dict)
        and (not channel_prefix or name.startswith(channel_prefix))
    }
    channel_metrics = {
        name: _summarize_channel(channel_state)
        for name, channel_state in selected_channels.items()
    }

    summary = {
        "channel_count": len(channel_metrics),
        "request_count": 0,
        "queue_wait_event_count": 0,
        "total_queue_wait_seconds": 0.0,
        "total_upstream_processing_seconds": 0.0,
        "retry_after_event_count": 0,
        "total_retry_after_seconds": 0.0,
        "cooldown_event_count": 0,
        "total_cooldown_seconds": 0.0,
        "rate_limit_response_count": 0,
        "max_queue_wait_seconds": 0.0,
    }
    for channel_summary in channel_metrics.values():
        summary["request_count"] += channel_summary["request_count"]
        summary["queue_wait_event_count"] += channel_summary["queue_wait_event_count"]
        summary["total_queue_wait_seconds"] += channel_summary[
            "total_queue_wait_seconds"
        ]
        summary["total_upstream_processing_seconds"] += channel_summary[
            "total_upstream_processing_seconds"
        ]
        summary["retry_after_event_count"] += channel_summary["retry_after_event_count"]
        summary["total_retry_after_seconds"] += channel_summary[
            "total_retry_after_seconds"
        ]
        summary["cooldown_event_count"] += channel_summary["cooldown_event_count"]
        summary["total_cooldown_seconds"] += channel_summary["total_cooldown_seconds"]
        summary["rate_limit_response_count"] += channel_summary[
            "rate_limit_response_count"
        ]
        summary["max_queue_wait_seconds"] = max(
            summary["max_queue_wait_seconds"],
            channel_summary["max_queue_wait_seconds"],
        )

    request_count = summary["request_count"]
    summary["total_queue_wait_seconds"] = _round_metric(
        summary["total_queue_wait_seconds"]
    )
    summary["total_upstream_processing_seconds"] = _round_metric(
        summary["total_upstream_processing_seconds"]
    )
    summary["total_retry_after_seconds"] = _round_metric(
        summary["total_retry_after_seconds"]
    )
    summary["total_cooldown_seconds"] = _round_metric(summary["total_cooldown_seconds"])
    summary["max_queue_wait_seconds"] = _round_metric(summary["max_queue_wait_seconds"])
    summary["avg_queue_wait_seconds"] = (
        _round_metric(summary["total_queue_wait_seconds"] / request_count)
        if request_count
        else 0.0
    )
    summary["avg_upstream_processing_seconds"] = (
        _round_metric(summary["total_upstream_processing_seconds"] / request_count)
        if request_count
        else 0.0
    )
    summary["time_breakdown_seconds"] = {
        "queue_wait": summary["total_queue_wait_seconds"],
        "upstream_processing": summary["total_upstream_processing_seconds"],
        "retry_after": summary["total_retry_after_seconds"],
        "cooldown": summary["total_cooldown_seconds"],
    }

    return {
        "shared_throttle_supported": shared_throttle_supported(),
        "state_path": str(_state_path()),
        "lock_path": str(_lock_path()),
        "summary": summary,
        "channels": channel_metrics,
    }


def record_request_outcome(
    channel: str = "llm",
    *,
    queue_wait_seconds: float = 0.0,
    upstream_processing_seconds: float = 0.0,
    status_code: int | None = None,
    retry_after_seconds: float | None = None,
) -> None:
    state_path = _state_path()
    lock_path = _lock_path()

    now = time.time()

    def _mutate(state: dict) -> dict:
        channel_state = _ensure_channel_state(state, channel)
        request_count = _coerce_int(channel_state.get("request_count"), 0) + 1
        queue_wait_seconds_value = _round_metric(queue_wait_seconds)
        upstream_processing_seconds_value = _round_metric(upstream_processing_seconds)

        channel_state["request_count"] = request_count
        channel_state["total_queue_wait_seconds"] = _round_metric(
            _coerce_float(channel_state.get("total_queue_wait_seconds"), 0.0)
            + queue_wait_seconds_value
        )
        channel_state["last_queue_wait_seconds"] = queue_wait_seconds_value
        if queue_wait_seconds_value > 0:
            channel_state["queue_wait_event_count"] = (
                _coerce_int(channel_state.get("queue_wait_event_count"), 0) + 1
            )
        channel_state["max_queue_wait_seconds"] = _round_metric(
            max(
                _coerce_float(channel_state.get("max_queue_wait_seconds"), 0.0),
                queue_wait_seconds_value,
            )
        )
        channel_state["total_upstream_processing_seconds"] = _round_metric(
            _coerce_float(
                channel_state.get("total_upstream_processing_seconds"),
                0.0,
            )
            + upstream_processing_seconds_value
        )
        channel_state["last_upstream_processing_seconds"] = (
            upstream_processing_seconds_value
        )
        if status_code is not None:
            channel_state["last_status_code"] = int(status_code)
            if int(status_code) == 429:
                channel_state["rate_limit_response_count"] = (
                    _coerce_int(channel_state.get("rate_limit_response_count"), 0) + 1
                )
        if retry_after_seconds is not None and retry_after_seconds > 0:
            retry_after_value = _round_metric(retry_after_seconds)
            channel_state["retry_after_event_count"] = (
                _coerce_int(channel_state.get("retry_after_event_count"), 0) + 1
            )
            channel_state["total_retry_after_seconds"] = _round_metric(
                _coerce_float(channel_state.get("total_retry_after_seconds"), 0.0)
                + retry_after_value
            )
            channel_state["last_retry_after_seconds"] = retry_after_value

        channel_state["last_request_finished_at"] = _round_metric(now)
        channel_state["updated_at"] = _round_metric(now)
        return state

    if not shared_throttle_supported():
        state = _mutate(_load_state(state_path))
        _save_state(state_path, state)
        return

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _mutate(_load_state(state_path))
        _save_state(state_path, state)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def reserve_api_slot(channel: str = "llm", role: str | None = None) -> float:
    """Reserve the next outbound API slot across parallel processes.

    Returns the number of seconds the caller should wait before making
    the next API call.
    """

    max_rps = _resolve_max_rps(channel, role=role)
    if max_rps <= 0:
        return 0.0

    min_interval = 1.0 / max_rps
    jitter_ratio = _resolve_jitter_ratio(role=role)
    max_wait_seconds = _resolve_max_wait_seconds(role=role)

    state_path = _state_path()
    lock_path = _lock_path()

    if not shared_throttle_supported():
        return 0.0

    now = time.time()
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _load_state(state_path)
        channels = state.get("channels")
        if not isinstance(channels, dict):
            channels = {}

        channel_state = channels.get(channel)
        if not isinstance(channel_state, dict):
            channel_state = {}

        next_allowed_ts = channel_state.get("next_allowed_ts", 0.0)
        try:
            next_allowed_ts = float(next_allowed_ts)
        except (TypeError, ValueError):
            next_allowed_ts = 0.0

        base_wait = max(0.0, next_allowed_ts - now)
        jitter_wait = random.uniform(0.0, min_interval * jitter_ratio)
        total_wait = min(max_wait_seconds, base_wait + jitter_wait)

        reserved_at = now + total_wait
        channel_state["next_allowed_ts"] = reserved_at + min_interval
        channel_state["updated_at"] = now
        channels[channel] = channel_state
        state["channels"] = channels
        _save_state(state_path, state)

        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return total_wait


def reserve_concurrency_lease(
    lease_scope: str,
    *,
    role: str | None = None,
    limit: int | None = None,
    holder: str | None = None,
) -> tuple[str | None, float]:
    """Try to reserve a shared concurrency lease for one upstream request.

    Returns a `(lease_id, wait_seconds)` tuple. When a lease is granted,
    `lease_id` is non-empty and `wait_seconds` is zero. When capacity is full,
    `lease_id` is `None` and `wait_seconds` is a small retry hint.
    """

    if not shared_throttle_supported():
        return None, 0.0

    lease_limit = (
        limit
        if limit is not None and limit > 0
        else _resolve_concurrency_lease_limit(role=role)
    )
    if lease_limit <= 0:
        return None, 0.0

    retry_hint_seconds = max(
        0.01,
        _parse_float_env("WORK_ISSUE_CONCURRENCY_LEASE_POLL_SECONDS", 0.05),
    )
    ttl_seconds = _resolve_concurrency_lease_ttl_seconds(role=role)

    state_path = _state_path()
    lock_path = _lock_path()
    now = time.time()

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _load_state(state_path)
        scope_state = _ensure_lease_scope_state(state, lease_scope)
        _prune_expired_leases(scope_state, now)
        leases = scope_state.get("leases")
        if not isinstance(leases, dict):
            leases = {}
            scope_state["leases"] = leases

        scope_state["lease_limit"] = lease_limit
        scope_state["updated_at"] = _round_metric(now)

        if len(leases) < lease_limit:
            lease_id = uuid.uuid4().hex
            leases[lease_id] = {
                "holder": holder or "",
                "acquired_at": _round_metric(now),
                "expires_at": _round_metric(now + ttl_seconds),
            }
            scope_state["lease_grant_count"] = (
                _coerce_int(scope_state.get("lease_grant_count"), 0) + 1
            )
            scope_state["active_lease_count"] = len(leases)
            scope_state["max_active_leases"] = max(
                _coerce_int(scope_state.get("max_active_leases"), 0),
                len(leases),
            )
            _save_state(state_path, state)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            return lease_id, 0.0

        scope_state["lease_wait_event_count"] = (
            _coerce_int(scope_state.get("lease_wait_event_count"), 0) + 1
        )
        scope_state["last_wait_hint_seconds"] = _round_metric(retry_hint_seconds)
        scope_state["updated_at"] = _round_metric(now)
        _save_state(state_path, state)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return None, retry_hint_seconds


def release_concurrency_lease(lease_scope: str, lease_id: str) -> bool:
    """Release a previously granted shared concurrency lease."""

    if not shared_throttle_supported() or not lease_scope or not lease_id:
        return False

    state_path = _state_path()
    lock_path = _lock_path()
    now = time.time()

    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _load_state(state_path)
        scope_state = _ensure_lease_scope_state(state, lease_scope)
        _prune_expired_leases(scope_state, now)
        leases = scope_state.get("leases")
        if not isinstance(leases, dict):
            leases = {}
            scope_state["leases"] = leases

        removed = leases.pop(lease_id, None)
        if removed is not None:
            scope_state["lease_release_count"] = (
                _coerce_int(scope_state.get("lease_release_count"), 0) + 1
            )
        scope_state["active_lease_count"] = len(leases)
        scope_state["updated_at"] = _round_metric(now)
        _save_state(state_path, state)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return removed is not None


def extract_retry_after_seconds(text: str) -> float | None:
    if not text:
        return None

    retry_after = re.search(r"retry[- ]after[^0-9]*(\d+)", text, flags=re.IGNORECASE)
    if retry_after:
        try:
            return float(retry_after.group(1))
        except ValueError:
            return None

    try_again = re.search(
        r"try again in\s+(?:(\d+)m)?\s*(?:(\d+)s)?",
        text,
        flags=re.IGNORECASE,
    )
    if try_again:
        minutes = int(try_again.group(1) or "0")
        seconds = int(try_again.group(2) or "0")
        total = (minutes * 60) + seconds
        if total > 0:
            return float(total)

    return None


def apply_rate_limit_penalty(
    channel: str = "llm",
    penalty_seconds: float | None = None,
    role: str | None = None,
) -> float:
    """Set a shared cooldown window after rate-limit responses.

    Returns the applied cooldown seconds.
    """
    cooldown = (
        penalty_seconds
        if penalty_seconds is not None and penalty_seconds > 0
        else _resolve_rate_limit_cooldown_seconds(role=role)
    )

    state_path = _state_path()
    lock_path = _lock_path()

    if not shared_throttle_supported():
        return cooldown

    now = time.time()
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        state = _load_state(state_path)
        channel_state = _ensure_channel_state(state, channel)

        next_allowed_ts = channel_state.get("next_allowed_ts", 0.0)
        try:
            next_allowed_ts = float(next_allowed_ts)
        except (TypeError, ValueError):
            next_allowed_ts = 0.0

        channel_state["next_allowed_ts"] = max(next_allowed_ts, now + cooldown)
        channel_state["cooldown_event_count"] = (
            _coerce_int(channel_state.get("cooldown_event_count"), 0) + 1
        )
        channel_state["total_cooldown_seconds"] = _round_metric(
            _coerce_float(channel_state.get("total_cooldown_seconds"), 0.0) + cooldown
        )
        channel_state["last_cooldown_seconds"] = _round_metric(cooldown)
        channel_state["updated_at"] = _round_metric(now)
        _save_state(state_path, state)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return cooldown
