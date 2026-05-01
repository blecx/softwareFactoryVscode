from __future__ import annotations

import json
from argparse import Namespace
from typing import Any

from scripts import noninteractive_gh


def test_build_noninteractive_env_disables_pagers(monkeypatch) -> None:
    monkeypatch.setenv("GH_PAGER", "less")
    monkeypatch.setenv("PAGER", "most")
    env = noninteractive_gh.build_noninteractive_env()

    assert env["GH_PAGER"] == "cat"
    assert env["PAGER"] == "cat"
    assert env["LESS"] == "FRX"


def test_build_pr_checks_payload_summarizes_rollup(monkeypatch) -> None:
    sample_payload: dict[str, Any] = {
        "number": 68,
        "title": "Example PR",
        "url": "https://example.test/pr/68",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "Python",
                "workflowName": "CI",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://example.test/python",
                "startedAt": "2026-04-19T21:00:00Z",
                "completedAt": "2026-04-19T21:01:00Z",
            },
            {
                "__typename": "CheckRun",
                "name": "Docker",
                "workflowName": "CI",
                "status": "IN_PROGRESS",
                "conclusion": "",
                "detailsUrl": "https://example.test/docker",
                "startedAt": "2026-04-19T21:00:00Z",
                "completedAt": None,
            },
        ],
    }

    monkeypatch.setattr(noninteractive_gh, "run_gh_json", lambda args: sample_payload)

    payload = noninteractive_gh.build_pr_checks_payload(
        Namespace(
            selector="68",
            repo="blecx/softwareFactoryVscode",
            wait=False,
            poll_interval_seconds=15,
            timeout_seconds=600,
        )
    )

    assert payload["query"]["kind"] == "pr-checks"
    assert payload["query"]["watch_mode"] is False
    assert payload["query"]["state_source"] == "github-pr-statuscheckrollup"
    assert payload["summary"]["overall"] == "pending"
    assert payload["summary"]["successful"] == 1
    assert payload["summary"]["pending"] == 1
    assert payload["checks"][0]["detailsUrl"] == "https://example.test/python"
    assert payload["wait"]["enabled"] is False
    assert payload["wait"]["timedOut"] is False


def test_build_pr_checks_payload_waits_until_success(monkeypatch) -> None:
    pending_payload: dict[str, Any] = {
        "number": 68,
        "title": "Example PR",
        "url": "https://example.test/pr/68",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "Aggregate",
                "workflowName": "CI",
                "status": "IN_PROGRESS",
                "conclusion": "",
                "detailsUrl": "https://example.test/aggregate",
                "startedAt": "2026-04-30T16:22:50Z",
                "completedAt": None,
            }
        ],
    }
    success_payload: dict[str, Any] = {
        **pending_payload,
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "Aggregate",
                "workflowName": "CI",
                "status": "COMPLETED",
                "conclusion": "SUCCESS",
                "detailsUrl": "https://example.test/aggregate",
                "startedAt": "2026-04-30T16:22:50Z",
                "completedAt": "2026-04-30T16:30:00Z",
            }
        ],
    }
    payloads = iter([pending_payload, success_payload])

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    clock = _Clock()
    monkeypatch.setattr(noninteractive_gh, "run_gh_json", lambda args: next(payloads))
    monkeypatch.setattr(noninteractive_gh.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(noninteractive_gh.time, "sleep", clock.sleep)

    payload = noninteractive_gh.build_pr_checks_payload(
        Namespace(
            selector="68",
            repo="blecx/softwareFactoryVscode",
            wait=True,
            poll_interval_seconds=15,
            timeout_seconds=600,
        )
    )

    assert payload["query"]["watch_mode"] is True
    assert payload["query"]["state_source"] == "github-pr-statuscheckrollup"
    assert payload["summary"]["overall"] == "success"
    assert payload["wait"]["enabled"] is True
    assert payload["wait"]["timedOut"] is False
    assert payload["wait"]["attempts"] == 2
    assert payload["wait"]["elapsedSeconds"] == 15


def test_build_pr_checks_payload_times_out_pending_wait(monkeypatch) -> None:
    pending_payload: dict[str, Any] = {
        "number": 68,
        "title": "Example PR",
        "url": "https://example.test/pr/68",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "Aggregate",
                "workflowName": "CI",
                "status": "IN_PROGRESS",
                "conclusion": "",
                "detailsUrl": "https://example.test/aggregate",
                "startedAt": "2026-04-30T16:22:50Z",
                "completedAt": None,
            }
        ],
    }

    class _Clock:
        def __init__(self) -> None:
            self.now = 0.0

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.now += seconds

    clock = _Clock()
    monkeypatch.setattr(noninteractive_gh, "run_gh_json", lambda args: pending_payload)
    monkeypatch.setattr(noninteractive_gh.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(noninteractive_gh.time, "sleep", clock.sleep)

    payload = noninteractive_gh.build_pr_checks_payload(
        Namespace(
            selector="68",
            repo="blecx/softwareFactoryVscode",
            wait=True,
            poll_interval_seconds=5,
            timeout_seconds=10,
        )
    )

    assert payload["summary"]["overall"] == "pending-timeout"
    assert payload["query"]["state_source"] == "github-pr-statuscheckrollup"
    assert payload["wait"]["enabled"] is True
    assert payload["wait"]["timedOut"] is True
    assert payload["wait"]["attempts"] == 3
    assert payload["wait"]["elapsedSeconds"] == 10


def test_main_pr_checks_outputs_machine_friendly_json(monkeypatch, capsys) -> None:
    expected_payload = {
        "query": {
            "kind": "pr-checks",
            "selector": "68",
            "repo": "",
            "pager_disabled": True,
            "watch_mode": False,
            "state_source": "github-pr-statuscheckrollup",
        },
        "pr": {
            "number": 68,
            "title": "Example PR",
            "url": "https://example.test/pr/68",
        },
        "summary": {"overall": "success", "total": 1},
        "checks": [],
    }

    monkeypatch.setattr(
        noninteractive_gh,
        "build_pr_checks_payload",
        lambda args: expected_payload,
    )

    exit_code = noninteractive_gh.main(["pr-checks", "68"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert json.loads(captured.out) == expected_payload
