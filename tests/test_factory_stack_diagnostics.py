from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

import scripts.factory_stack as factory_stack


@dataclass
class FakeSnapshot:
    unpersisted_active_id: str | None = None
    persisted_active_id: str | None = None
    persisted_runtime_state: str = "stopped"
    target_dir: str = "/fake/repo"
    expected_workspace_urls: dict = field(default_factory=dict)
    mcp_ports_healthy: bool = True
    lifecycle_state: str = "installed"
    selection: str = "default"
    recovery: str = "none"
    last_transition_at: str | None = None
    last_transition_reason_codes: tuple = ()
    readiness: str = "operational"

    @property
    def ready(self) -> bool:
        return True


@dataclass
class FakeConfig:
    factory_instance_id: str = "test-instance"
    project_workspace_id: str = "test-ws-id"
    target_dir: Path = Path("/fake/repo")
    compose_project_name: str = "test-compose"
    shared_service_mode: str = "isolated"
    runtime_mode: str = "docker"
    port_index: int = 1
    base_port: int = 8000
    mcp_server_urls: dict[str, str] = field(default_factory=dict)


def test_build_preflight_json_payload():
    config = FakeConfig()
    snapshot = FakeSnapshot()
    report = {
        "config": config,
        "snapshot": snapshot,
        "status": "ready",
        "recommended_action": "start",
        "reason_codes": ["already_running"],
        "issues": [],
        "blocking_services": [],
        "readiness": "ready",
    }
    registry = {
        "workspaces": {
            "test-instance": {
                "target_dir": "/fake/repo",
                "last_active": "2024-01-01T00:00:00Z",
            }
        },
        "active_workspace": "test-instance",
    }

    payload = factory_stack.build_preflight_json_payload(
        report,
        registry,
        command="preflight",
        runtime_state="running",
        notices=["test notice"],
    )

    assert payload["command"] == "preflight"
    assert payload["notices"] == ["test notice"]

    workspace = payload["workspace"]
    assert workspace["instance_id"] == "test-instance"
    assert workspace["active"] is True
    assert workspace["runtime_mode"] == "docker"

    runtime = payload["runtime"]
    assert runtime["runtime_state"] == "running"
    assert runtime["persisted_runtime_state"] == "stopped"

    preflight = payload["preflight"]
    assert preflight["status"] == "ready"
    assert preflight["recommended_action"] == "start"
    assert preflight["reason_codes"] == ["already_running"]
    assert preflight["readiness"] == "ready"


def test_build_status_json_payload():
    config = FakeConfig()
    snapshot = FakeSnapshot(
        expected_workspace_urls={"context7": "http://localhost:8001"}
    )
    preflight = {
        "config": config,
        "snapshot": snapshot,
        "status": "online",
        "recommended_action": "none",
        "reason_codes": [],
        "issues": [],
        "blocking_services": [],
        "readiness": "operational",
    }
    registry = {
        "workspaces": {
            "test-instance": {
                "target_dir": "/fake/repo",
                "last_active": "2024-01-01T00:00:00Z",
            }
        },
        "active_workspace": "test-instance",
    }

    payload = factory_stack.build_status_json_payload(
        config,
        registry,
        preflight,
        snapshot,
        runtime_state="running",
        active=True,
        installed_version="1.0.0",
        head_commit="abcdef",
        lock_commit="abcdef",
        needs_rebuild=False,
        notices=[],
    )

    assert payload["command"] == "status"
    assert payload["workspace"]["port_index"] == 1
    assert payload["workspace"]["active"] is True

    runtime = payload["runtime"]
    assert runtime["installed_version"] == "1.0.0"
    assert runtime["factory_commit"] == "abcdef"
    assert runtime["needs_rebuild"] is False

    diagnostics = payload["diagnostics"]
    assert diagnostics["effective_workspace_urls"] == {
        "context7": "http://localhost:8001"
    }
