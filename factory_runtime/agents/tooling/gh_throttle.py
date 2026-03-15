import os
import re
import subprocess
import time
from typing import Optional, Sequence


_LAST_GH_CALL_TS: Optional[float] = None


def _resolve_min_interval_seconds(override: Optional[int]) -> int:
    if override is not None:
        return int(override)
    return int(os.environ.get("GH_MIN_INTERVAL_SECONDS", "3") or "3")


def _resolve_max_attempts() -> int:
    raw = os.environ.get("GH_THROTTLE_MAX_ATTEMPTS", "3") or "3"
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _resolve_base_backoff_seconds() -> float:
    raw = os.environ.get("GH_THROTTLE_BACKOFF_SECONDS", "15") or "15"
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 15.0


def _is_rate_limited(output: str) -> bool:
    text = (output or "").lower()
    return any(
        token in text
        for token in (
            "rate limit",
            "secondary rate limit",
            "too many requests",
            "http 429",
        )
    )


def _extract_retry_after_seconds(output: str) -> Optional[float]:
    text = output or ""

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


def run_gh_throttled(
    args: Sequence[str],
    *,
    min_interval_seconds: Optional[int] = None,
    **subprocess_kwargs,
) -> subprocess.CompletedProcess[str]:
    """Run a `gh ...` command with a minimum interval between invocations.

    This helps avoid secondary GitHub API rate limits when automation issues many
    `gh` subprocess calls in a tight loop.

    Configuration:
    - `GH_MIN_INTERVAL_SECONDS` (default: 3)
    - `GH_THROTTLE_MAX_ATTEMPTS` (default: 3)
    - `GH_THROTTLE_BACKOFF_SECONDS` (default: 15)
    - Or pass `min_interval_seconds` explicitly.
    """

    global _LAST_GH_CALL_TS

    interval = _resolve_min_interval_seconds(min_interval_seconds)
    max_attempts = _resolve_max_attempts()
    base_backoff = _resolve_base_backoff_seconds()

    check_requested = bool(subprocess_kwargs.pop("check", False))
    command = list(args)

    attempt = 1
    while True:
        if interval > 0 and _LAST_GH_CALL_TS is not None:
            elapsed = time.monotonic() - _LAST_GH_CALL_TS
            remaining = interval - elapsed
            if remaining > 0:
                time.sleep(remaining)

        _LAST_GH_CALL_TS = time.monotonic()

        result = subprocess.run(  # noqa: S603 (controlled internal CLI invocation)
            command,
            check=False,
            **subprocess_kwargs,
        )

        if result.returncode == 0:
            return result

        combined_output = "\n".join(
            part for part in ((result.stderr or ""), (result.stdout or "")) if part
        )

        if attempt >= max_attempts or not _is_rate_limited(combined_output):
            if check_requested:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    command,
                    output=result.stdout,
                    stderr=result.stderr,
                )
            return result

        retry_after = _extract_retry_after_seconds(combined_output)
        if retry_after is not None:
            sleep_seconds = retry_after
        else:
            sleep_seconds = base_backoff * (2 ** (attempt - 1))
        time.sleep(sleep_seconds)
        attempt += 1
