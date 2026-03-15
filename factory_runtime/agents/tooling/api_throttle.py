import json
import os
import random
import re
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


def _parse_float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return default


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _resolve_max_rps() -> float:
    value = _parse_float_env("WORK_ISSUE_MAX_RPS", 0.10)
    return max(0.0, value)


def _resolve_jitter_ratio() -> float:
    value = _parse_float_env("WORK_ISSUE_RPS_JITTER", 0.25)
    return _clamp(value, 0.0, 1.0)


def _resolve_max_wait_seconds() -> float:
    value = _parse_float_env("WORK_ISSUE_MAX_THROTTLE_WAIT_SECONDS", 180.0)
    return max(1.0, value)


def _resolve_rate_limit_cooldown_seconds() -> float:
    value = _parse_float_env("WORK_ISSUE_RATE_LIMIT_COOLDOWN_SECONDS", 45.0)
    return max(1.0, value)


def _state_path() -> Path:
    configured = (os.environ.get("WORK_ISSUE_API_THROTTLE_STATE_FILE") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(".tmp") / "api-throttle-state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _lock_path() -> Path:
    configured = (os.environ.get("WORK_ISSUE_API_THROTTLE_LOCK_FILE") or "").strip()
    if configured:
        path = Path(configured)
    else:
        path = Path(".tmp") / "api-throttle.lock"
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


def reserve_api_slot(channel: str = "llm") -> float:
    """Reserve the next outbound API slot across parallel processes.

    Returns the number of seconds the caller should wait before making
    the next API call.
    """

    max_rps = _resolve_max_rps()
    if max_rps <= 0:
        return 0.0

    min_interval = 1.0 / max_rps
    jitter_ratio = _resolve_jitter_ratio()
    max_wait_seconds = _resolve_max_wait_seconds()

    state_path = _state_path()
    lock_path = _lock_path()

    if fcntl is None:
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
    channel: str = "llm", penalty_seconds: float | None = None
) -> float:
    """Set a shared cooldown window after rate-limit responses.

    Returns the applied cooldown seconds.
    """
    cooldown = (
        penalty_seconds
        if penalty_seconds is not None and penalty_seconds > 0
        else _resolve_rate_limit_cooldown_seconds()
    )

    state_path = _state_path()
    lock_path = _lock_path()

    if fcntl is None:
        return cooldown

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

        channel_state["next_allowed_ts"] = max(next_allowed_ts, now + cooldown)
        channel_state["updated_at"] = now
        channels[channel] = channel_state
        state["channels"] = channels
        _save_state(state_path, state)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return cooldown
