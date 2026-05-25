import json
import os

import pytest

from scripts.workflow_preflight import run_preflight


def test_preflight_valid_issue():
    result = run_preflight("work on issue", is_human_activated=False)
    assert result["safe_to_continue"] is True
    assert result["required_agent"] == "@resolve-issue"
    assert len(result["blockers"]) == 0


def test_preflight_unknown_input():
    result = run_preflight("generate a snake game", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert "Unknown or ambiguous task kind." in result["blockers"]


def test_preflight_bypass_without_human():
    result = run_preflight("bypass the check", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any("bypass" in str(b).lower() for b in result["blockers"])


def test_preflight_bypass_with_human():
    result = run_preflight("@harness-bypass-resolution", is_human_activated=True)
    assert result["safe_to_continue"] is True
    assert result["required_agent"] == "@harness-bypass-resolution"
    assert len(result["blockers"]) == 0


def test_preflight_missing_manifest(tmp_path):
    # Pass a path that definitely does not exist
    result = run_preflight(
        "work on issue",
        is_human_activated=False,
        manifest_path=str(tmp_path / "does_not_exist.json"),
    )
    assert result["safe_to_continue"] is False
    assert "Missing routing manifest:" in str(result["blockers"])


def test_preflight_missing_language_config(tmp_path):
    result = run_preflight(
        "work on issue",
        is_human_activated=False,
        config_path=str(tmp_path / "does_not_exist.yml"),
    )
    assert result["safe_to_continue"] is False
    assert "Missing factory workflow language config:" in str(result["blockers"])


def test_preflight_invalid_manifest_schema(tmp_path):
    manifest_path = tmp_path / "invalid_manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "agent": "@valid-agent",
                    "task_kinds": ["test"],
                    "requirements": [],
                    "human_only": False,
                },
                {"agent": "@invalid-agent", "task_kinds": ["test"]},
            ]
        )
    )
    result = run_preflight(
        "work on issue", is_human_activated=False, manifest_path=str(manifest_path)
    )
    assert result["safe_to_continue"] is False
    assert any(
        "Routing manifest schema validation failed" in b for b in result["blockers"]
    )
    assert any(
        "Invalid route @invalid-agent: missing requirements, human_only" in b
        for b in result["blockers"]
    )


def test_preflight_red_team_ambiguous_continue():
    result = run_preflight("continue", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any("ask which issue set is approved" in str(b) for b in result["blockers"])


def test_preflight_red_team_execute_the_plan():
    result = run_preflight("execute the plan", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any("ask which issue set is approved" in str(b) for b in result["blockers"])


def test_preflight_red_team_ready():
    result = run_preflight("ready", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any(
        "Validate against CI and pipeline reality" in str(b) for b in result["blockers"]
    )


def test_preflight_red_team_close_it():
    result = run_preflight("close it", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any("Unknown or ambiguous task kind" in str(b) for b in result["blockers"])


def test_preflight_red_team_stale_state():
    result = run_preflight("stale continuation", is_human_activated=False)
    assert result["safe_to_continue"] is False
    assert any("ask which issue set is approved" in str(b) for b in result["blockers"])
