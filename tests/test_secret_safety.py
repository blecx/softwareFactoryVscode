from __future__ import annotations

import importlib
import json

import pytest

from factory_runtime.apps.mcp.github_ops.audit_store import AuditRecord, AuditStore
from factory_runtime.apps.mcp.github_ops.policy import (
    GitHubOpsPolicy,
    GitHubOpsPolicyError,
)


def test_audit_store_redacts_command_and_output(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CONTEXT7_API_KEY", "ctx-live-secret")
    store = AuditStore(tmp_path)

    record = AuditRecord(
        run_id="run-123",
        tool="github_ops_pr_view",
        timestamp_utc="2026-04-25T00:00:00Z",
        status="ok",
        exit_code=0,
        duration_sec=0.1,
        cwd="/workspace",
        command=[
            "env",
            "CONTEXT7_API_KEY=ctx-live-secret",
            'payload={"api_key":"ctx-live-secret"}',
        ],
        output='{"api_key":"ctx-live-secret"}\nGITHUB_TOKEN=ctx-live-secret\n',
    )

    saved_path = store.save(record)
    saved = json.loads(saved_path.read_text(encoding="utf-8"))

    assert all("ctx-live-secret" not in part for part in saved["command"])
    assert "ctx-live-secret" not in saved["output"]
    assert "[REDACTED]" in saved["output"]


def test_github_ops_policy_rejects_placeholder_allowlist_in_production(
    monkeypatch,
) -> None:
    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")

    with pytest.raises(
        GitHubOpsPolicyError,
        match="Production runtime requires non-placeholder GITHUB_OPS_ALLOWED_REPOS",
    ):
        GitHubOpsPolicy.from_env(
            allowed_repos_env="YOUR_ORG/YOUR_REPO",
            default_allowed_repos=["YOUR_ORG/YOUR_REPO"],
        )


def test_bus_set_live_key_rejects_in_production_mode(
    monkeypatch,
    tmp_path,
) -> None:
    override_path = tmp_path / "runtime_override.json"
    monkeypatch.setenv("FACTORY_RUNTIME_MODE", "production")
    monkeypatch.setenv("AGENT_BUS_DB_PATH", ":memory:")
    monkeypatch.setenv("LLM_OVERRIDE_PATH", str(override_path))

    module = importlib.import_module("factory_runtime.apps.mcp.agent_bus.mcp_server")
    module = importlib.reload(module)

    with pytest.raises(
        ValueError,
        match="Dynamic live-key injection via bus_set_live_key is disabled",
    ):
        module.bus_set_live_key("live-secret")

    assert not override_path.exists()
