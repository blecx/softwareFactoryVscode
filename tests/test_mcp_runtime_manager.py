from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
