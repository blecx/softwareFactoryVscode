from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import factory_runtime.mcp_runtime.manager as runtime_manager_module
from factory_runtime.mcp_runtime import (
    MCPRuntimeManager,
    ReadinessStatus,
    ReasonCode,
    RecommendedAction,
    RuntimeLifecycleState,
    RuntimeProfileName,
    ServiceInstanceStatus,
    ServiceScope,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
factory_workspace = runtime_manager_module.factory_workspace


def build_full_service_inventory(
    config: Any,
    *,
    agent_worker_status: str = "Up 10 seconds (healthy)",
) -> dict[str, dict[str, object]]:
    return {
        "mock-llm-gateway": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/mock-llm-gateway:latest",
            "published_ports": [config.ports["PORT_TUI"]],
        },
        "mcp-memory": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/mcp-memory:latest",
            "published_ports": [config.ports["MEMORY_MCP_PORT"]],
        },
        "mcp-agent-bus": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/mcp-agent-bus:latest",
            "published_ports": [config.ports["AGENT_BUS_PORT"]],
        },
        "approval-gate": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/approval-gate:latest",
            "published_ports": [config.ports["APPROVAL_GATE_PORT"]],
        },
        "agent-worker": {
            "status": agent_worker_status,
            "image": "factory/agent-worker:latest",
            "published_ports": [],
        },
        "context7": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/context7:latest",
            "published_ports": [config.ports["PORT_CONTEXT7"]],
        },
        "bash-gateway-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/bash-gateway:latest",
            "published_ports": [config.ports["PORT_BASH"]],
        },
        "git-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/git-mcp:latest",
            "published_ports": [config.ports["PORT_FS"]],
        },
        "search-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/search-mcp:latest",
            "published_ports": [config.ports["PORT_GIT"]],
        },
        "filesystem-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/filesystem-mcp:latest",
            "published_ports": [config.ports["PORT_SEARCH"]],
        },
        "docker-compose-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/docker-compose-mcp:latest",
            "published_ports": [config.ports["PORT_COMPOSE"]],
        },
        "test-runner-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/test-runner-mcp:latest",
            "published_ports": [config.ports["PORT_TEST"]],
        },
        "offline-docs-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/offline-docs-mcp:latest",
            "published_ports": [config.ports["PORT_DOCS"]],
        },
        "github-ops-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory/github-ops-mcp:latest",
            "published_ports": [config.ports["PORT_GITHUB"]],
        },
    }


def prepare_workspace(
    tmp_path: Path,
    *,
    registry_path: Path,
    shared_mode: bool = False,
) -> tuple[Path, Path, Any, Path]:
    target_repo = tmp_path / "target-project"
    repo_root = target_repo / ".copilot/softwareFactoryVscode"
    repo_root.mkdir(parents=True)
    (repo_root / ".copilot" / "config").mkdir(parents=True)
    (repo_root / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    if shared_mode:
        env_path = repo_root / ".factory.env"
        env_path.write_text(
            "\n".join(
                [
                    f"TARGET_WORKSPACE_PATH={target_repo}",
                    "PROJECT_WORKSPACE_ID=target-project",
                    "COMPOSE_PROJECT_NAME=factory_target-project",
                    f"FACTORY_DIR={repo_root}",
                    "FACTORY_SHARED_SERVICE_MODE=shared",
                    "FACTORY_TENANCY_MODE=shared",
                    "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                    "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                    "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                    "CONTEXT7_API_KEY=",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=repo_root,
        registry_path=registry_path,
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        registry_path=registry_path,
        runtime_state="running",
        active=False,
    )
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    return target_repo, repo_root, config, env_path


def test_runtime_catalog_exposes_workspace_and_harness_profiles() -> None:
    manager = MCPRuntimeManager()
    catalog = manager.load_catalog()
    harness_selection = catalog.select_profiles([RuntimeProfileName.HARNESS_DEFAULT])

    assert RuntimeProfileName.WORKSPACE_DEFAULT in catalog.profiles
    assert RuntimeProfileName.HARNESS_DEFAULT in catalog.profiles
    assert catalog.services["mcp-memory"].scope == ServiceScope.SHARED_CAPABLE
    assert catalog.services["github-ops-mcp"].workspace_server_name == "githubOps"
    assert harness_selection.names == (RuntimeProfileName.HARNESS_DEFAULT,)
    assert set(harness_selection.required_services) == {
        "mcp-memory",
        "mcp-agent-bus",
        "git-mcp",
        "search-mcp",
        "filesystem-mcp",
        "github-ops-mcp",
    }


def test_manager_builds_canonical_snapshot_for_workspace_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    target_repo, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )
    manager = MCPRuntimeManager(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.workspace_id == config.project_workspace_id
    assert snapshot.instance_id == config.factory_instance_id
    assert snapshot.target_dir == target_repo
    assert snapshot.selection.installed is True
    assert snapshot.selection.active is False
    assert snapshot.selection.profiles.names == (RuntimeProfileName.WORKSPACE_DEFAULT,)
    assert snapshot.lifecycle_state == RuntimeLifecycleState.RUNNING
    assert snapshot.readiness is not None
    assert snapshot.readiness.status == ReadinessStatus.READY
    assert snapshot.services["mcp-memory"].status == ServiceInstanceStatus.RUNNING
    assert snapshot.as_dict()["selection"]["profiles"]["names"] == ["workspace-default"]


def test_manager_normalizes_workspace_url_drift_reason_codes(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    target_repo, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    workspace_path = target_repo / "software-factory.code-workspace"
    workspace_data = json.loads(workspace_path.read_text(encoding="utf-8"))
    workspace_data["settings"]["mcp"]["servers"]["context7"][
        "url"
    ] = "http://127.0.0.1:3510/mcp"
    workspace_path.write_text(
        json.dumps(workspace_data, indent=2) + "\n",
        encoding="utf-8",
    )

    manager = MCPRuntimeManager(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness
    assert readiness is not None

    assert readiness.status == ReadinessStatus.CONFIG_DRIFT
    assert readiness.recommended_action == RecommendedAction.REBOOTSTRAP
    assert ReasonCode.WORKSPACE_URL_DRIFT in readiness.reason_codes
    assert any(
        "Generated workspace MCP URL drift detected" in issue
        for issue in readiness.issues
    )


def test_manager_marks_promoted_shared_services_as_external(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    _, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
        shared_mode=True,
    )

    inventory = build_full_service_inventory(config)
    for service_name in ("mcp-memory", "mcp-agent-bus", "approval-gate"):
        del inventory[service_name]

    manager = MCPRuntimeManager(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: inventory,
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness
    assert readiness is not None

    assert snapshot.services["mcp-memory"].status == ServiceInstanceStatus.EXTERNAL
    assert snapshot.services["mcp-agent-bus"].status == ServiceInstanceStatus.EXTERNAL
    assert snapshot.services["approval-gate"].status == ServiceInstanceStatus.EXTERNAL
    assert readiness.status == ReadinessStatus.READY
    assert snapshot.shared_mode == "shared"


def test_manager_repair_contract_is_reason_coded_placeholder() -> None:
    manager = MCPRuntimeManager()

    result = manager.repair()

    assert result.attempted is False
    assert result.success is False
    assert result.attempted_steps == (runtime_manager_module.RepairStep.REPROBE,)
    assert result.reason_codes == (ReasonCode.REPAIR_NOT_IMPLEMENTED,)
