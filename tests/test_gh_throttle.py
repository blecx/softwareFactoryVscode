from __future__ import annotations

import subprocess

import pytest

from factory_runtime.agents.tooling import gh_throttle


def test_run_gh_throttled_applies_default_watchdog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, check, **kwargs):
        captured["command"] = command
        captured["check"] = check
        captured["timeout"] = kwargs.get("timeout")
        return subprocess.CompletedProcess(command, 0, stdout="{}", stderr="")

    monkeypatch.setenv("GH_THROTTLE_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr(gh_throttle, "_LAST_GH_CALL_TS", None)
    monkeypatch.setattr(gh_throttle.subprocess, "run", fake_run)

    result = gh_throttle.run_gh_throttled(
        ["gh", "issue", "view", "323"],
        capture_output=True,
        text=True,
        min_interval_seconds=0,
    )

    assert result.returncode == 0
    assert captured["timeout"] == 7.0


def test_run_gh_throttled_respects_explicit_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(command, check, **kwargs):
        captured["timeout"] = kwargs.get("timeout")
        raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout", 0))

    monkeypatch.setenv("GH_THROTTLE_TIMEOUT_SECONDS", "7")
    monkeypatch.setattr(gh_throttle, "_LAST_GH_CALL_TS", None)
    monkeypatch.setattr(gh_throttle.subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired):
        gh_throttle.run_gh_throttled(
            ["gh", "issue", "view", "323"],
            capture_output=True,
            text=True,
            timeout=2,
            min_interval_seconds=0,
        )

    assert captured["timeout"] == 2
