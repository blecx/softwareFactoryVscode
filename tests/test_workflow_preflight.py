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
