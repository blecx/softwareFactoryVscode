from __future__ import annotations

import errno
import json
from pathlib import Path
from typing import Any

import pytest

import factory_runtime.mcp_runtime.manager as runtime_manager_module
from factory_runtime.mcp_runtime import (
    MCPRuntimeManager,
    ReadinessResult,
    ReadinessStatus,
    ReasonCode,
    RecommendedAction,
    RecoveryClassification,
    RepairResult,
    RepairStep,
    RuntimeActionTrigger,
    RuntimeLifecycleState,
    RuntimeMode,
    RuntimeProfileName,
    RuntimeSnapshot,
    SelectionMetadata,
    ServiceInstanceStatus,
    ServiceRuntimeRecord,
    ServiceScope,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
factory_workspace = runtime_manager_module.factory_workspace


def build_manager_with_successful_probes(
    *,
    registry_path: Path | None = None,
    **kwargs: Any,
) -> MCPRuntimeManager:
    return MCPRuntimeManager(
        registry_path=registry_path,
        http_probe_func=lambda url, timeout, allow_http_error: None,
        mcp_initialize_probe=lambda url, timeout, workspace_id: None,
        **kwargs,
    )


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

    env_path = repo_root / ".factory.env"
    if shared_mode:
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
                    "CONTEXT7_API_KEY=test-context7-key",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        env_path.write_text("CONTEXT7_API_KEY=test-context7-key\n", encoding="utf-8")

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
    assert RuntimeProfileName.WORKSPACE_PRODUCTION in catalog.profiles
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
    manager = build_manager_with_successful_probes(registry_path=registry_path)
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


def test_manager_recovers_running_lifecycle_from_persisted_degraded_state(
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
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id][
        "runtime_state"
    ] = RuntimeLifecycleState.DEGRADED.value
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.persisted_runtime_state == RuntimeLifecycleState.DEGRADED.value
    assert snapshot.lifecycle_state == RuntimeLifecycleState.RUNNING
    assert snapshot.readiness is not None
    assert snapshot.readiness.status == ReadinessStatus.READY


def test_manager_builds_production_snapshot_without_mock_gateway(
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
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "FACTORY_RUNTIME_MODE=production\n"
        + "GITHUB_TOKEN=test-github-token\n",
        encoding="utf-8",
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode\n",
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness

    assert snapshot.runtime_mode == RuntimeMode.PRODUCTION
    assert snapshot.selection.profiles.names == (
        RuntimeProfileName.WORKSPACE_PRODUCTION,
    )
    assert "mock-llm-gateway" not in snapshot.services
    assert readiness is not None
    assert readiness.status == ReadinessStatus.READY


def test_manager_blocks_production_snapshot_when_live_github_token_is_missing(
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
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "FACTORY_RUNTIME_MODE=production\n"
        + "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode\n",
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness

    assert snapshot.runtime_mode == RuntimeMode.PRODUCTION
    assert snapshot.selection.profiles.names == (
        RuntimeProfileName.WORKSPACE_PRODUCTION,
    )
    assert "mock-llm-gateway" not in snapshot.services
    assert readiness is not None
    assert readiness.status == ReadinessStatus.CONFIG_DRIFT
    assert ReasonCode.MISSING_SECRET in readiness.reason_codes
    assert any("GITHUB_TOKEN" in issue for issue in readiness.issues)


def test_manager_builds_production_snapshot_with_live_llm_config_api_key(
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
    )
    configs_dir = repo_root / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)
    (configs_dir / "llm.default.json").write_text(
        json.dumps(
            {
                "provider": "github",
                "base_url": "https://models.github.ai/inference",
                "api_key": "live-config-github-token",
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "FACTORY_RUNTIME_MODE=production\n"
        + "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode\n",
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness

    assert readiness is not None
    assert readiness.status == ReadinessStatus.READY
    assert snapshot.runtime_mode == RuntimeMode.PRODUCTION


def test_manager_blocks_production_snapshot_when_github_ops_allowlist_is_placeholder(
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
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "FACTORY_RUNTIME_MODE=production\n"
        + "GITHUB_TOKEN=test-github-token\n"
        + "GITHUB_OPS_ALLOWED_REPOS=YOUR_ORG/YOUR_REPO\n",
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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
    assert ReasonCode.MISSING_CONFIG in readiness.reason_codes
    assert any("GITHUB_OPS_ALLOWED_REPOS" in issue for issue in readiness.issues)


def test_manager_blocks_production_snapshot_when_override_file_exists(
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
    )
    override_path = repo_root / "configs" / "runtime_override.json"
    override_path.parent.mkdir(parents=True, exist_ok=True)
    override_path.write_text(
        json.dumps({"api_key": "live-override-key"}), encoding="utf-8"
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8")
        + "FACTORY_RUNTIME_MODE=production\n"
        + "GITHUB_TOKEN=test-github-token\n"
        + "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode\n",
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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
    assert ReasonCode.PROFILE_MISMATCH in readiness.reason_codes
    assert any("LLM_OVERRIDE_PATH" in issue for issue in readiness.issues)


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

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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


def test_manager_blocks_snapshot_when_required_secret_is_missing(
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
    )
    env_path.write_text(
        env_path.read_text(encoding="utf-8").replace(
            "CONTEXT7_API_KEY=test-context7-key",
            "CONTEXT7_API_KEY=",
        ),
        encoding="utf-8",
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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
    assert ReasonCode.MISSING_SECRET in readiness.reason_codes
    assert any("CONTEXT7_API_KEY" in issue for issue in readiness.issues)


def test_manager_blocks_snapshot_when_required_mount_is_missing(
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
    )
    missing_mount = (
        Path(config.env_values["FACTORY_DATA_DIR"])
        / "memory"
        / config.factory_instance_id
    )
    if missing_mount.exists():
        missing_mount.rmdir()

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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
    assert ReasonCode.MISSING_MOUNT in readiness.reason_codes
    assert any("mount/resource path" in issue for issue in readiness.issues)


def test_manager_reports_degraded_when_endpoint_probe_fails_for_running_service(
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
    )

    manager = MCPRuntimeManager(
        registry_path=registry_path,
        http_probe_func=lambda url, timeout, allow_http_error: (
            "connection refused"
            if f":{config.ports['PORT_CONTEXT7']}/mcp" in url
            else None
        ),
        mcp_initialize_probe=lambda url, timeout, workspace_id: None,
    )
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness
    assert readiness is not None

    assert readiness.status == ReadinessStatus.DEGRADED
    assert ReasonCode.ENDPOINT_UNREACHABLE in readiness.reason_codes
    assert any("context7" in issue for issue in readiness.issues)


def test_manager_reports_degraded_when_mcp_initialize_fails_for_running_service(
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
    )

    manager = MCPRuntimeManager(
        registry_path=registry_path,
        http_probe_func=lambda url, timeout, allow_http_error: None,
        mcp_initialize_probe=lambda url, timeout, workspace_id: (
            "initialize rejected by server"
            if f":{config.ports['PORT_GITHUB']}/mcp" in url
            else None
        ),
    )
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    readiness = snapshot.readiness
    assert readiness is not None

    assert readiness.status == ReadinessStatus.DEGRADED
    assert ReasonCode.MCP_INITIALIZE_FAILED in readiness.reason_codes
    assert any("github-ops-mcp" in issue for issue in readiness.issues)


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

    manager = build_manager_with_successful_probes(registry_path=registry_path)
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


def test_manager_snapshot_as_dict_is_machine_readable_for_shared_topology(
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

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: inventory,
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    snapshot_dict = snapshot.as_dict()

    assert snapshot_dict["workspace_id"] == config.project_workspace_id
    assert snapshot_dict["instance_id"] == config.factory_instance_id
    assert snapshot_dict["selection"]["installed"] is True
    assert snapshot_dict["runtime_topology"]["mode"] == "shared"
    assert snapshot_dict["shared_mode"] == "shared"
    assert snapshot_dict["shared_mode_diagnostics"]["tenant_identity_required"] is True
    assert snapshot_dict["services"]["mcp-memory"]["status"] == "external"
    assert snapshot_dict["services"]["mcp-memory"]["workspace_owned"] is False
    assert snapshot_dict["readiness"]["status"] == "ready"


def build_repairable_snapshot(
    manager: MCPRuntimeManager,
    config: Any,
    *,
    readiness: ReadinessResult,
    lifecycle_state: RuntimeLifecycleState = RuntimeLifecycleState.DEGRADED,
    service_name: str = "github-ops-mcp",
) -> RuntimeSnapshot:
    catalog = manager.load_catalog()
    selection = SelectionMetadata(
        installed=True,
        active=False,
        profiles=catalog.select_profiles((RuntimeProfileName.WORKSPACE_DEFAULT,)),
    )
    service_entry = catalog.services[service_name]
    return RuntimeSnapshot(
        workspace_id=config.project_workspace_id,
        instance_id=config.factory_instance_id,
        target_dir=config.target_dir,
        factory_dir=config.factory_dir,
        compose_project_name=config.compose_project_name,
        lifecycle_state=lifecycle_state,
        selection=selection,
        persisted_runtime_state=lifecycle_state.value,
        services={
            service_name: ServiceRuntimeRecord(
                service_name=service_name,
                runtime_identity=service_entry.runtime_identity,
                service_kind=service_entry.service_kind,
                scope=service_entry.scope,
                topology_mode="workspace",
                workspace_owned=True,
                status=ServiceInstanceStatus.DEGRADED,
                reason_codes=readiness.reason_codes,
            )
        },
        catalog=catalog,
        readiness=readiness,
    )


def test_manager_repair_trips_bounded_circuit_breaker(
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
    )
    manager = MCPRuntimeManager(registry_path=registry_path, max_repair_failures=2)
    readiness = ReadinessResult(
        status=ReadinessStatus.DEGRADED,
        recommended_action=RecommendedAction.REPAIR,
        ready=False,
        reason_codes=(ReasonCode.ENDPOINT_UNREACHABLE,),
        blocking_services=("github-ops-mcp",),
        issues=("github-ops-mcp endpoint is unreachable",),
    )
    snapshot = build_repairable_snapshot(manager, config, readiness=readiness)
    compose_actions: list[tuple[str, ...]] = []

    monkeypatch.setattr(manager, "build_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        manager,
        "_prepare_runtime_config_for_actions",
        lambda *args, **kwargs: object(),
    )
    monkeypatch.setattr(
        manager,
        "_run_compose_action",
        lambda repo_root, env_file, action: compose_actions.append(tuple(action)),
    )

    first_result = manager.repair(repo_root, env_file=env_path)
    second_result = manager.repair(repo_root, env_file=env_path)
    third_result = manager.repair(repo_root, env_file=env_path)

    assert first_result.attempted is True
    assert first_result.success is False
    assert first_result.attempted_steps == (
        RepairStep.REPROBE,
        RepairStep.RECREATE_SERVICE,
        RepairStep.SURFACE_TERMINAL_FAILURE,
    )
    assert ReasonCode.REPAIR_CIRCUIT_BREAKER not in first_result.reason_codes

    assert second_result.attempted is True
    assert second_result.success is False
    assert ReasonCode.REPAIR_CIRCUIT_BREAKER in second_result.reason_codes

    assert third_result.attempted is False
    assert third_result.success is False
    assert third_result.attempted_steps == (RepairStep.SURFACE_TERMINAL_FAILURE,)
    assert third_result.reason_codes == (
        ReasonCode.REPAIR_CIRCUIT_BREAKER,
        ReasonCode.TERMINAL_RUNTIME_FAILURE,
    )
    assert len(compose_actions) == 2

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert record["repair_failure_count"] == 2
    assert record["repair_circuit_breaker_tripped_at"]
    assert record["last_runtime_action"] == RuntimeActionTrigger.REPAIR.value
    assert record["last_runtime_action_reason_codes"] == [
        ReasonCode.REPAIR_CIRCUIT_BREAKER.value,
        ReasonCode.TERMINAL_RUNTIME_FAILURE.value,
    ]


def test_manager_repair_distinguishes_host_level_failures(
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
    )
    manager = build_manager_with_successful_probes(registry_path=registry_path)
    snapshot = build_repairable_snapshot(
        manager,
        config,
        readiness=ReadinessResult(
            status=ReadinessStatus.DOCKER_UNAVAILABLE,
            recommended_action=RecommendedAction.INSTALL_DOCKER,
            ready=False,
            reason_codes=(ReasonCode.DOCKER_UNAVAILABLE,),
            issues=("Docker CLI is not available on PATH.",),
        ),
        service_name="mcp-memory",
    )

    monkeypatch.setattr(manager, "build_snapshot", lambda *args, **kwargs: snapshot)
    monkeypatch.setattr(
        manager,
        "_prepare_runtime_config_for_actions",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("host failures must not reach action prep")
        ),
    )
    monkeypatch.setattr(
        manager,
        "_run_compose_action",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("host failures must not run compose actions")
        ),
    )

    result = manager.repair(repo_root, env_file=env_path)

    assert result.attempted is True
    assert result.success is False
    assert result.attempted_steps == (
        RepairStep.REPROBE,
        RepairStep.SURFACE_TERMINAL_FAILURE,
    )
    assert result.reason_codes == (
        ReasonCode.REPAIR_REPROBE,
        ReasonCode.HOST_DOCKER_UNAVAILABLE,
        ReasonCode.TERMINAL_RUNTIME_FAILURE,
    )


def test_manager_build_snapshot_exposes_resume_unsafe_recovery_metadata(
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
    )

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    record.update(
        {
            "runtime_state": RuntimeLifecycleState.REPAIRING.value,
            "execution_lease_present": True,
            "execution_lease_holder": "agent-worker",
            "execution_lease_renewed_at": "2026-04-21T10:00:00Z",
            "last_runtime_action": RuntimeActionTrigger.REPAIR.value,
            "last_runtime_action_at": "2026-04-21T10:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.REPAIR_REPROBE.value],
            "last_completed_tool_call_boundary_at": None,
            "repair_failure_count": 1,
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.recovery is not None
    assert snapshot.selection.execution_lease is not None
    assert snapshot.selection.execution_lease.present is True
    assert snapshot.selection.execution_lease.holder == "agent-worker"
    assert snapshot.recovery.classification == RecoveryClassification.RESUME_UNSAFE
    assert snapshot.recovery.completed_tool_call_boundary is False
    assert snapshot.recovery.last_trigger == RuntimeActionTrigger.REPAIR
    assert snapshot.recovery.repair_failure_count == 1


def test_manager_build_snapshot_does_not_infer_activity_lease_from_history(
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
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["active_workspace"] = ""
    registry["workspaces"][config.factory_instance_id][
        "last_activated_at"
    ] = "2026-04-21T09:00:00Z"
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.selection.active is False
    assert snapshot.selection.activity_lease is not None
    assert snapshot.selection.activity_lease.present is False
    assert snapshot.selection.activity_lease.renewed_at == "2026-04-21T09:00:00Z"


def test_manager_build_snapshot_preserves_bounded_suspended_state(
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
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id][
        "runtime_state"
    ] = RuntimeLifecycleState.SUSPENDED.value
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(manager, "_collect_service_inventory", lambda _compose_name: {})

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.persisted_runtime_state == RuntimeLifecycleState.SUSPENDED.value
    assert snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED
    assert snapshot.readiness is not None
    assert snapshot.readiness.status == ReadinessStatus.NEEDS_RAMP_UP
    assert snapshot.readiness.recommended_action == RecommendedAction.RESUME
    assert snapshot.recovery is not None
    assert snapshot.recovery.classification == RecoveryClassification.RESUME_SAFE


def test_manager_suspend_records_safe_resume_boundary(
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
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)

    inventory_state = {"mode": "running"}

    def fake_collect_service_inventory(
        _compose_name: str,
    ) -> dict[str, dict[str, object]]:
        if inventory_state["mode"] == "running":
            return build_full_service_inventory(config)
        return {}

    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        fake_collect_service_inventory,
    )

    stop_calls: list[tuple[Path, Path | None, bool, bool]] = []

    class FakeStackModule:
        def stop_stack(
            self,
            repo_root_arg: Path,
            *,
            env_file: Path | None = None,
            remove_volumes: bool = False,
            preserve_runtime_state: bool = False,
        ) -> Path | None:
            stop_calls.append(
                (repo_root_arg, env_file, remove_volumes, preserve_runtime_state)
            )
            inventory_state["mode"] = "stopped"
            return env_file

    monkeypatch.setattr(
        manager,
        "_load_factory_stack_module",
        lambda: FakeStackModule(),
    )

    snapshot = manager.suspend(
        repo_root,
        env_file=env_path,
        completed_tool_call_boundary=True,
    )

    assert stop_calls == [(repo_root, env_path, False, True)]
    assert snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED
    assert snapshot.readiness is not None
    assert snapshot.readiness.recommended_action == RecommendedAction.RESUME
    assert snapshot.recovery is not None
    assert snapshot.recovery.classification == RecoveryClassification.RESUME_SAFE
    assert snapshot.recovery.completed_tool_call_boundary is True
    assert snapshot.recovery.last_trigger == RuntimeActionTrigger.SUSPEND
    assert ReasonCode.SUSPEND_REQUESTED in snapshot.recovery.last_reason_codes

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert record["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert record["last_runtime_action"] == RuntimeActionTrigger.SUSPEND.value
    assert (
        ReasonCode.SUSPEND_REQUESTED.value in record["last_runtime_action_reason_codes"]
    )
    assert record["last_completed_tool_call_boundary_at"]


def test_manager_suspend_with_execution_lease_marks_resume_unsafe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "runtime.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    _, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id]["execution_lease_present"] = True
    registry["workspaces"][config.factory_instance_id][
        "execution_lease_holder"
    ] = "copilot-session"
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)

    inventory_state = {"mode": "running"}
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: (
            build_full_service_inventory(config)
            if inventory_state["mode"] == "running"
            else {}
        ),
    )

    class FakeStackModule:
        def stop_stack(
            self,
            repo_root_arg: Path,
            *,
            env_file: Path | None = None,
            remove_volumes: bool = False,
            preserve_runtime_state: bool = False,
        ) -> Path | None:
            assert repo_root_arg == repo_root
            assert env_file == env_path
            assert remove_volumes is False
            assert preserve_runtime_state is True
            inventory_state["mode"] = "stopped"
            return env_file

    monkeypatch.setattr(
        manager,
        "_load_factory_stack_module",
        lambda: FakeStackModule(),
    )

    snapshot = manager.suspend(repo_root, env_file=env_path)

    assert snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED
    assert snapshot.recovery is not None
    assert snapshot.recovery.classification == RecoveryClassification.RESUME_UNSAFE
    assert snapshot.recovery.completed_tool_call_boundary is False

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert record["last_completed_tool_call_boundary_at"] is None


def test_manager_backup_requires_bounded_suspended_state(
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
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    with pytest.raises(
        RuntimeError,
        match="requires the bounded `suspended` lifecycle state",
    ):
        manager.backup(repo_root, env_file=env_path)


def test_manager_backup_creates_timestamped_bundle_with_checksums(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    memory_db = data_root / "memory" / config.factory_instance_id / "memory.db"
    agent_bus_db = data_root / "bus" / config.factory_instance_id / "agent_bus.db"
    memory_db.write_text("memory-state\n", encoding="utf-8")
    agent_bus_db.write_text("agent-bus-state\n", encoding="utf-8")

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T08:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T08:00:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    result = manager.backup(repo_root, env_file=env_path)

    bundle_path = Path(result["bundle_path"])
    manifest_path = bundle_path / "bundle-manifest.json"
    checksums_path = bundle_path / "checksums.sha256"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    checksums = checksums_path.read_text(encoding="utf-8")
    runtime_snapshot = json.loads(
        (bundle_path / "metadata" / "runtime-snapshot.json").read_text(encoding="utf-8")
    )
    registry_snapshot = json.loads(
        (bundle_path / "metadata" / "workspace-registry.json").read_text(
            encoding="utf-8"
        )
    )

    assert bundle_path.parent == data_root / "backups" / config.factory_instance_id
    assert bundle_path.name.startswith("backup-")
    assert result["required_precondition"] == RuntimeLifecycleState.SUSPENDED.value
    assert result["captured_artifact_count"] == 6
    assert manifest["required_precondition"] == RuntimeLifecycleState.SUSPENDED.value
    assert manifest["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert manifest["recovery_classification"] == "resume-safe"
    assert manifest["completed_tool_call_boundary"] is True

    artifact_map = {
        artifact["logical_name"]: artifact for artifact in manifest["artifacts"]
    }
    assert set(artifact_map) == {
        "memory-db",
        "agent-bus-db",
        "factory-env",
        "runtime-manifest",
        "runtime-snapshot",
        "workspace-registry",
    }
    assert (bundle_path / artifact_map["memory-db"]["bundle_relative_path"]).read_text(
        encoding="utf-8"
    ) == "memory-state\n"
    assert (
        bundle_path / artifact_map["agent-bus-db"]["bundle_relative_path"]
    ).read_text(encoding="utf-8") == "agent-bus-state\n"
    assert "workspace/.copilot/softwareFactoryVscode/.factory.env" in checksums
    assert (
        "workspace/.copilot/softwareFactoryVscode/.tmp/runtime-manifest.json"
        in checksums
    )
    assert runtime_snapshot["lifecycle_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert registry_snapshot["workspace_record_source"] == "registry"
    assert (
        registry_snapshot["workspace_record"]["factory_instance_id"]
        == config.factory_instance_id
    )

    updated_registry = factory_workspace.load_registry(registry_path)
    updated_record = updated_registry["workspaces"][config.factory_instance_id]
    assert updated_record["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert updated_record["last_runtime_action"] == RuntimeActionTrigger.BACKUP.value
    assert (
        ReasonCode.BACKUP_REQUESTED.value
        in updated_record["last_runtime_action_reason_codes"]
    )
    assert (
        updated_record["last_completed_tool_call_boundary_at"] == "2026-04-25T08:00:05Z"
    )


def test_manager_restore_rehydrates_suspended_runtime_from_backup_bundle(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    memory_db = data_root / "memory" / config.factory_instance_id / "memory.db"
    agent_bus_db = data_root / "bus" / config.factory_instance_id / "agent_bus.db"
    memory_db.write_text("memory-state\n", encoding="utf-8")
    agent_bus_db.write_text("agent-bus-state\n", encoding="utf-8")

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T08:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T08:00:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    backup_result = manager.backup(repo_root, env_file=env_path)
    bundle_path = Path(backup_result["bundle_path"])

    memory_db.write_text("mutated-memory\n", encoding="utf-8")
    agent_bus_db.write_text("mutated-bus\n", encoding="utf-8")
    manager._remove_runtime_data_dirs(config)
    env_path.unlink()
    config.runtime_manifest_path.unlink()
    manager._persist_runtime_deleted_record(
        target_path=config.target_dir,
        factory_dir=repo_root,
        config=config,
        trigger=RuntimeActionTrigger.CLEANUP,
        reason_codes=(),
    )

    restore_result = manager.restore(repo_root, bundle_path=bundle_path)

    assert memory_db.read_text(encoding="utf-8") == "memory-state\n"
    assert agent_bus_db.read_text(encoding="utf-8") == "agent-bus-state\n"
    assert env_path.exists()
    assert config.runtime_manifest_path.exists()
    assert restore_result["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert restore_result["preflight_status"] == ReadinessStatus.NEEDS_RAMP_UP.value
    assert restore_result["recommended_action"] == RecommendedAction.RESUME.value
    assert (
        restore_result["recovery_classification"]
        == RecoveryClassification.RESUME_SAFE.value
    )
    assert restore_result["completed_tool_call_boundary"] is True

    restored_snapshot = manager.build_snapshot(repo_root, env_file=env_path)
    assert restored_snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED
    assert restored_snapshot.recovery is not None
    assert restored_snapshot.recovery.last_trigger == RuntimeActionTrigger.RESTORE

    updated_registry = factory_workspace.load_registry(registry_path)
    updated_record = updated_registry["workspaces"][config.factory_instance_id]
    assert updated_record["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert updated_record["last_runtime_action"] == RuntimeActionTrigger.RESTORE.value
    assert (
        ReasonCode.RESTORE_REQUESTED.value
        in updated_record["last_runtime_action_reason_codes"]
    )
    assert (
        updated_record["last_completed_tool_call_boundary_at"] == "2026-04-25T08:00:05Z"
    )


def test_manager_restore_does_not_require_source_metadata_copy(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    memory_db = data_root / "memory" / config.factory_instance_id / "memory.db"
    agent_bus_db = data_root / "bus" / config.factory_instance_id / "agent_bus.db"
    memory_db.write_text("memory-state\n", encoding="utf-8")
    agent_bus_db.write_text("agent-bus-state\n", encoding="utf-8")

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T08:30:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T08:30:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    backup_result = manager.backup(repo_root, env_file=env_path)
    bundle_path = Path(backup_result["bundle_path"])

    manager._remove_runtime_data_dirs(config)
    env_path.unlink()
    config.runtime_manifest_path.unlink()
    manager._persist_runtime_deleted_record(
        target_path=config.target_dir,
        factory_dir=repo_root,
        config=config,
        trigger=RuntimeActionTrigger.CLEANUP,
        reason_codes=(),
    )

    def fail_copystat(
        src: str | bytes | Path,
        dst: str | bytes | Path,
        *,
        follow_symlinks: bool = True,
    ) -> None:
        del src, dst, follow_symlinks
        raise PermissionError("metadata copy blocked")

    monkeypatch.setattr(runtime_manager_module.shutil, "copystat", fail_copystat)

    restore_result = manager.restore(repo_root, bundle_path=bundle_path)

    assert restore_result["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert memory_db.read_text(encoding="utf-8") == "memory-state\n"
    assert agent_bus_db.read_text(encoding="utf-8") == "agent-bus-state\n"
    assert not list(memory_db.parent.glob("*.restore-tmp"))
    assert not list(agent_bus_db.parent.glob("*.restore-tmp"))


def test_manager_restore_retries_when_temp_destination_path_is_missing(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    memory_db = data_root / "memory" / config.factory_instance_id / "memory.db"
    agent_bus_db = data_root / "bus" / config.factory_instance_id / "agent_bus.db"
    memory_db.write_text("memory-state\n", encoding="utf-8")
    agent_bus_db.write_text("agent-bus-state\n", encoding="utf-8")

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T08:45:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T08:45:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    backup_result = manager.backup(repo_root, env_file=env_path)
    bundle_path = Path(backup_result["bundle_path"])

    manager._remove_runtime_data_dirs(config)
    env_path.unlink()
    config.runtime_manifest_path.unlink()
    manager._persist_runtime_deleted_record(
        target_path=config.target_dir,
        factory_dir=repo_root,
        config=config,
        trigger=RuntimeActionTrigger.CLEANUP,
        reason_codes=(),
    )

    real_copyfile = runtime_manager_module.shutil.copyfile
    memory_temp_path = memory_db.with_name(memory_db.name + ".restore-tmp")
    failed_once = {"value": False}

    def flaky_copyfile(
        src: str | bytes | Path,
        dst: str | bytes | Path,
        *args: object,
        **kwargs: object,
    ) -> object:
        if not failed_once["value"] and Path(dst) == memory_temp_path:
            failed_once["value"] = True
            raise FileNotFoundError(
                errno.ENOENT,
                "No such file or directory",
                str(dst),
            )
        return real_copyfile(src, dst, *args, **kwargs)

    monkeypatch.setattr(runtime_manager_module.shutil, "copyfile", flaky_copyfile)

    restore_result = manager.restore(repo_root, bundle_path=bundle_path)

    assert failed_once["value"] is True
    assert restore_result["runtime_state"] == RuntimeLifecycleState.SUSPENDED.value
    assert memory_db.read_text(encoding="utf-8") == "memory-state\n"
    assert agent_bus_db.read_text(encoding="utf-8") == "agent-bus-state\n"
    assert not list(memory_db.parent.glob("*.restore-tmp"))
    assert not list(agent_bus_db.parent.glob("*.restore-tmp"))


def test_manager_restore_requires_resume_safe_bundle(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    (data_root / "memory" / config.factory_instance_id / "memory.db").write_text(
        "memory-state\n",
        encoding="utf-8",
    )
    (data_root / "bus" / config.factory_instance_id / "agent_bus.db").write_text(
        "agent-bus-state\n",
        encoding="utf-8",
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T09:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T09:00:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    backup_result = manager.backup(repo_root, env_file=env_path)
    bundle_path = Path(backup_result["bundle_path"])
    manifest_path = bundle_path / "bundle-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["completed_tool_call_boundary"] = False
    manifest["recovery_classification"] = RecoveryClassification.RESUME_UNSAFE.value
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="resume-safe"):
        manager.restore(repo_root, bundle_path=bundle_path)


def test_manager_restore_rejects_invalid_bundle_size_bytes_metadata(
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
    )

    data_root = Path(config.env_values["FACTORY_DATA_DIR"])
    (data_root / "memory" / config.factory_instance_id / "memory.db").write_text(
        "memory-state\n",
        encoding="utf-8",
    )
    (data_root / "bus" / config.factory_instance_id / "agent_bus.db").write_text(
        "agent-bus-state\n",
        encoding="utf-8",
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-25T09:30:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-25T09:30:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: {},
    )

    backup_result = manager.backup(repo_root, env_file=env_path)
    bundle_path = Path(backup_result["bundle_path"])
    bundle_manifest = json.loads(
        (bundle_path / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    bundle_manifest["artifacts"][0]["size_bytes"] = "not-a-number"

    with pytest.raises(RuntimeError, match="invalid `size_bytes` value"):
        manager._validate_restore_bundle_artifacts(bundle_path, bundle_manifest)


def test_manager_restore_rejects_invalid_backed_up_port_metadata(
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
    _, _, config, _ = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    invalid_port_key = next(iter(factory_workspace.PORT_LAYOUT))

    with pytest.raises(RuntimeError, match="invalid port value"):
        manager._validate_restore_port_metadata(
            config,
            {"ports": {invalid_port_key: "not-a-number"}},
            {"ports": {}},
        )

    with pytest.raises(RuntimeError, match="invalid `port_index` value"):
        manager._validate_restore_port_metadata(
            config,
            {"ports": {}, "port_index": "not-a-number"},
            {"ports": {}},
        )


def test_manager_restore_requires_inventory_collection_when_docker_is_available(
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
    _, _, config, _ = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: (
            (_ for _ in ()).throw(RuntimeError("docker inspect failed"))
        ),
    )

    with pytest.raises(RuntimeError, match="inventory for compose project"):
        manager._validate_restore_runtime_stopped(config.compose_project_name)


def test_manager_resume_repairs_unready_suspended_runtime(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "runtime.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    _, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-21T12:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": "2026-04-21T12:00:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)

    degraded_inventory = build_full_service_inventory(config)
    degraded_inventory.pop("search-mcp")
    inventory_state = {"mode": "suspended"}

    def fake_collect_service_inventory(
        _compose_name: str,
    ) -> dict[str, dict[str, object]]:
        if inventory_state["mode"] == "healthy":
            return build_full_service_inventory(config)
        if inventory_state["mode"] == "degraded":
            return degraded_inventory
        return {}

    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        fake_collect_service_inventory,
    )

    start_calls: list[tuple[Path, Path | None, bool, bool, int, bool]] = []

    class FakeStackModule:
        def start_stack(
            self,
            repo_root_arg: Path,
            *,
            env_file: Path | None = None,
            build: bool = True,
            wait: bool = True,
            wait_timeout: int = 300,
            foreground: bool = False,
        ) -> Path | None:
            start_calls.append(
                (repo_root_arg, env_file, build, wait, wait_timeout, foreground)
            )
            factory_workspace.update_runtime_state(
                config.factory_instance_id,
                RuntimeLifecycleState.RUNNING.value,
                registry_path=registry_path,
            )
            inventory_state["mode"] = "degraded"
            return env_file

    monkeypatch.setattr(
        manager,
        "_load_factory_stack_module",
        lambda: FakeStackModule(),
    )

    repair_calls: list[
        tuple[Path, Path | None, tuple[RuntimeProfileName | str, ...] | None]
    ] = []

    def fake_repair(
        repo_root_arg: Path,
        *,
        env_file: Path | None = None,
        selected_profiles: tuple[RuntimeProfileName | str, ...] | None = None,
    ) -> RepairResult:
        repair_calls.append((repo_root_arg, env_file, selected_profiles))
        inventory_state["mode"] = "healthy"
        factory_workspace.update_runtime_state(
            config.factory_instance_id,
            RuntimeLifecycleState.RUNNING.value,
            registry_path=registry_path,
        )
        return RepairResult(
            attempted=True,
            success=True,
            attempted_steps=(RepairStep.RECREATE_SERVICE,),
            reason_codes=(ReasonCode.REPAIR_RECREATE,),
            details=("recreated missing service",),
            final_state=RuntimeLifecycleState.RUNNING,
        )

    monkeypatch.setattr(manager, "repair", fake_repair)

    snapshot = manager.resume(repo_root, env_file=env_path)

    assert start_calls == [(repo_root, env_path, False, True, 300, False)]
    assert repair_calls == [(repo_root, env_path, None)]
    assert snapshot.lifecycle_state == RuntimeLifecycleState.RUNNING
    assert snapshot.readiness is not None
    assert snapshot.readiness.ready is True
    assert snapshot.recovery is not None
    assert snapshot.recovery.last_trigger == RuntimeActionTrigger.RESUME
    assert snapshot.recovery.completed_tool_call_boundary is True
    assert ReasonCode.RESUME_REQUESTED in snapshot.recovery.last_reason_codes
    assert ReasonCode.RESUME_REPAIR_ATTEMPTED in snapshot.recovery.last_reason_codes
    assert ReasonCode.REPAIR_RECREATE in snapshot.recovery.last_reason_codes

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert record["runtime_state"] == RuntimeLifecycleState.RUNNING.value
    assert record["last_runtime_action"] == RuntimeActionTrigger.RESUME.value
    assert (
        ReasonCode.RESUME_REQUESTED.value in record["last_runtime_action_reason_codes"]
    )
    assert (
        ReasonCode.RESUME_REPAIR_ATTEMPTED.value
        in record["last_runtime_action_reason_codes"]
    )
    assert (
        ReasonCode.REPAIR_RECREATE.value in record["last_runtime_action_reason_codes"]
    )


def test_manager_resume_preserves_missing_boundary_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "runtime.json"
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        runtime_manager_module.factory_workspace,
        "ports_available",
        lambda ports: True,
    )
    _, repo_root, config, env_path = prepare_workspace(
        tmp_path,
        registry_path=registry_path,
    )

    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "runtime_state": RuntimeLifecycleState.SUSPENDED.value,
            "last_runtime_action": RuntimeActionTrigger.SUSPEND.value,
            "last_runtime_action_at": "2026-04-21T13:00:00Z",
            "last_runtime_action_reason_codes": [ReasonCode.SUSPEND_REQUESTED.value],
            "last_completed_tool_call_boundary_at": None,
            "execution_lease_present": True,
            "execution_lease_holder": "copilot-session",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = build_manager_with_successful_probes(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    inventory_state = {"mode": "suspended"}

    def fake_collect_service_inventory(
        _compose_name: str,
    ) -> dict[str, dict[str, object]]:
        if inventory_state["mode"] == "running":
            return build_full_service_inventory(config)
        return {}

    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        fake_collect_service_inventory,
    )

    class FakeStackModule:
        def start_stack(
            self,
            repo_root_arg: Path,
            *,
            env_file: Path | None = None,
            build: bool = True,
            wait: bool = True,
            wait_timeout: int = 300,
            foreground: bool = False,
        ) -> Path | None:
            assert repo_root_arg == repo_root
            assert env_file == env_path
            assert build is False
            assert wait is True
            assert wait_timeout == 300
            assert foreground is False
            factory_workspace.update_runtime_state(
                config.factory_instance_id,
                RuntimeLifecycleState.RUNNING.value,
                registry_path=registry_path,
            )
            inventory_state["mode"] = "running"
            return env_file

    monkeypatch.setattr(
        manager,
        "_load_factory_stack_module",
        lambda: FakeStackModule(),
    )

    snapshot = manager.resume(repo_root, env_file=env_path)

    assert snapshot.lifecycle_state == RuntimeLifecycleState.RUNNING
    assert snapshot.recovery is not None
    assert snapshot.recovery.completed_tool_call_boundary is False
    assert snapshot.recovery.last_completed_tool_call_at is None

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert record["last_runtime_action"] == RuntimeActionTrigger.RESUME.value
    assert record["last_completed_tool_call_boundary_at"] is None


def test_manager_build_snapshot_surfaces_manual_recovery_requirement(
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
    )

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    record.update(
        {
            "runtime_state": RuntimeLifecycleState.DEGRADED.value,
            "last_runtime_action": RuntimeActionTrigger.REPAIR.value,
            "last_runtime_action_at": "2026-04-21T11:00:00Z",
            "last_runtime_action_reason_codes": [
                ReasonCode.REPAIR_CIRCUIT_BREAKER.value,
                ReasonCode.TERMINAL_RUNTIME_FAILURE.value,
            ],
            "last_completed_tool_call_boundary_at": "2026-04-21T11:00:05Z",
            "repair_failure_count": 2,
            "repair_circuit_breaker_tripped_at": "2026-04-21T11:00:05Z",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    manager = MCPRuntimeManager(registry_path=registry_path)
    monkeypatch.setattr(manager, "_docker_available", lambda: True)
    monkeypatch.setattr(
        manager,
        "_collect_service_inventory",
        lambda _compose_name: build_full_service_inventory(config),
    )

    snapshot = manager.build_snapshot(repo_root, env_file=env_path)

    assert snapshot.recovery is not None
    assert snapshot.recovery.classification == (
        RecoveryClassification.MANUAL_RECOVERY_REQUIRED
    )
    assert snapshot.recovery.completed_tool_call_boundary is True
    assert snapshot.recovery.circuit_breaker_tripped is True
    assert snapshot.recovery.circuit_breaker_tripped_at == "2026-04-21T11:00:05Z"
    assert snapshot.recovery.last_reason_codes == (
        ReasonCode.REPAIR_CIRCUIT_BREAKER,
        ReasonCode.TERMINAL_RUNTIME_FAILURE,
    )
