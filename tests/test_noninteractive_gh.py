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
        Namespace(selector="68", repo="blecx/softwareFactoryVscode")
    )

    assert payload["query"]["kind"] == "pr-checks"
    assert payload["summary"]["overall"] == "pending"
    assert payload["summary"]["successful"] == 1
    assert payload["summary"]["pending"] == 1
    assert payload["checks"][0]["detailsUrl"] == "https://example.test/python"


def test_main_pr_checks_outputs_machine_friendly_json(monkeypatch, capsys) -> None:
    expected_payload = {
        "query": {
            "kind": "pr-checks",
            "selector": "68",
            "repo": "",
            "pager_disabled": True,
            "watch_mode": False,
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
