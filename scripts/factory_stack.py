#!/usr/bin/env python3
"""Canonical start/stop helper for the Software Factory runtime stack."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import factory_workspace

from factory_runtime.mcp_runtime import MCPRuntimeManager, RuntimeLifecycleState
from factory_runtime.mcp_runtime.models import serialize_contract_value

DEFAULT_WAIT_TIMEOUT = 300
DEFAULT_WORKSPACE_FILENAME = factory_workspace.DEFAULT_WORKSPACE_FILENAME
COMPOSE_FILES = [
    "compose/docker-compose.factory.yml",
    "compose/docker-compose.context7.yml",
    "compose/docker-compose.mcp-bash-gateway.yml",
    "compose/docker-compose.repo-fundamentals-mcp.yml",
    "compose/docker-compose.mcp-devops.yml",
    "compose/docker-compose.mcp-offline-docs.yml",
    "compose/docker-compose.mcp-github-ops.yml",
]
SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
PORT_MAPPING_PATTERN = re.compile(r"(?P<host>\d+)->(?P<container>\d+)/(?:tcp|udp)")
WORKSPACE_SERVICE_PORT_KEYS: dict[str, tuple[str, str]] = {
    "context7": ("context7", "PORT_CONTEXT7"),
    "bash-gateway-mcp": ("bashGateway", "PORT_BASH"),
    "git-mcp": ("git", "PORT_FS"),
    "search-mcp": ("search", "PORT_GIT"),
    "filesystem-mcp": ("filesystem", "PORT_SEARCH"),
    "docker-compose-mcp": ("dockerCompose", "PORT_COMPOSE"),
    "test-runner-mcp": ("testRunner", "PORT_TEST"),
    "offline-docs-mcp": ("offlineDocs", "PORT_DOCS"),
    "github-ops-mcp": ("githubOps", "PORT_GITHUB"),
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_env_file(repo_root: Path, env_file: Path | None = None) -> Path:
    if env_file is not None:
        return env_file.expanduser().resolve()

    candidates = [(repo_root / ".factory.env").resolve()]
    if len(repo_root.parents) > 1:
        companion_env = (
            repo_root.parents[1] / factory_workspace.FACTORY_DIRNAME / ".factory.env"
        ).resolve()
        if companion_env not in candidates:
            candidates.append(companion_env)

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return candidates[0]


def build_compose_command(
    repo_root: Path,
    env_file: Path,
    action: Sequence[str],
) -> list[str]:
    command = [
        "docker",
        "compose",
        "--project-directory",
        str(repo_root),
        "--env-file",
        str(env_file),
    ]
    for compose_file in COMPOSE_FILES:
        command.extend(["-f", str((repo_root / compose_file).resolve())])
    command.extend(action)
    return command


def run_compose_command(repo_root: Path, command: Sequence[str]) -> None:
    # Ensure system TEMP/TMPDIR variables reference existing directories
    # to prevent Docker BuildKit from crashing inside VS Code terminals (which inject their own TMPDIR paths).
    for env_var in ["TMPDIR", "TEMP", "TMP"]:
        tmp_path = os.environ.get(env_var)
        if tmp_path:
            try:
                Path(tmp_path).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass  # Ignore permission/creation errors if any

    subprocess.run(
        list(command),
        cwd=str(repo_root),
        check=True,
        text=True,
    )


def collect_running_services(compose_project_name: str) -> dict[str, str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            '{{.Label "com.docker.compose.service"}}|{{.Status}}',
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    services: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip() or "|" not in line:
            continue
        service, status = line.split("|", 1)
        services[service.strip()] = status.strip()
    return services


def parse_published_ports(ports_text: str) -> list[int]:
    published_ports = {
        int(match.group("host")) for match in PORT_MAPPING_PATTERN.finditer(ports_text)
    }
    return sorted(published_ports)


def collect_service_inventory(compose_project_name: str) -> dict[str, dict[str, Any]]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            '{{.Label "com.docker.compose.service"}}|{{.Status}}|{{.Image}}|{{.Ports}}',
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    inventory: dict[str, dict[str, Any]] = {}
    for line in result.stdout.splitlines():
        if not line.strip() or "|" not in line:
            continue
        service, status, image, ports_text = (line.split("|", 3) + ["", "", "", ""])[:4]
        inventory[service.strip()] = {
            "status": status.strip(),
            "image": image.strip(),
            "ports_text": ports_text.strip(),
            "published_ports": parse_published_ports(ports_text.strip()),
        }
    return inventory


def load_workspace_server_urls(
    target_dir: Path,
    workspace_file: str,
) -> dict[str, str]:
    workspace_path = target_dir / workspace_file
    config_data = load_json(workspace_path) if workspace_path.exists() else {}
    servers = config_data.get("settings", {}).get("mcp", {}).get("servers", {})
    urls: dict[str, str] = {}
    if not isinstance(servers, dict):
        return urls
    for name, data in servers.items():
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            urls[name] = data["url"]
    return urls


def build_expected_service_ports(
    config: factory_workspace.WorkspaceRuntimeConfig,
) -> dict[str, int]:
    workspace_owned_runtime_services = (
        factory_workspace.workspace_owned_runtime_services(config)
    )
    expected_ports = {
        service_name: config.ports[metadata["port_key"]]
        for service_name, metadata in factory_workspace.RUNTIME_SERVICE_CONTRACT.items()
        if metadata.get("port_key") and service_name in workspace_owned_runtime_services
    }
    expected_ports.update(
        {
            service_name: config.ports[port_key]
            for service_name, (
                _server_name,
                port_key,
            ) in WORKSPACE_SERVICE_PORT_KEYS.items()
        }
    )
    return expected_ports


def build_runtime_manager(
    *,
    workspace_file: str = DEFAULT_WORKSPACE_FILENAME,
) -> MCPRuntimeManager:
    return MCPRuntimeManager(
        default_workspace_file=workspace_file,
        docker_available_checker=lambda: shutil.which("docker") is not None,
        service_inventory_loader=collect_service_inventory,
        stack_module_loader=lambda: sys.modules[__name__],
    )


def build_service_inventory_report(
    snapshot: Any,
) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for service_name, service_record in snapshot.services.items():
        inventory[service_name] = {
            "status": service_record.docker_status,
            "image": "",
            "ports_text": "",
            "published_ports": list(service_record.published_ports),
        }
    return inventory


def build_preflight_report_from_snapshot(
    config: factory_workspace.WorkspaceRuntimeConfig,
    snapshot: Any,
) -> dict[str, Any]:
    readiness = snapshot.readiness
    if readiness is None:
        raise RuntimeError("Runtime snapshot did not include a readiness result.")

    return {
        "status": readiness.status.value,
        "recommended_action": readiness.recommended_action.value,
        "reason_codes": [code.value for code in readiness.reason_codes],
        "issues": list(readiness.issues),
        "blocking_services": list(readiness.blocking_services),
        "config": config,
        "runtime_mode": getattr(snapshot, "runtime_mode", config.runtime_mode),
        "workspace_urls": dict(snapshot.workspace_urls),
        "manifest_server_urls": dict(snapshot.manifest_server_urls),
        "manifest_health_urls": dict(snapshot.manifest_health_urls),
        "expected_service_ports": dict(snapshot.expected_service_ports),
        "service_inventory": build_service_inventory_report(snapshot),
        "runtime_topology": dict(snapshot.runtime_topology),
        "shared_mode_diagnostics": dict(snapshot.shared_mode_diagnostics),
        "snapshot": snapshot,
        "readiness": readiness,
    }


def serialize_machine_readable_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "as_dict") and callable(getattr(value, "as_dict")):
        return value.as_dict()
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): serialize_machine_readable_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [serialize_machine_readable_value(item) for item in value]
    serialized = serialize_contract_value(value)
    if serialized is not value:
        return serialized
    if hasattr(value, "__dict__"):
        return {
            str(key): serialize_machine_readable_value(item)
            for key, item in vars(value).items()
        }
    return serialized


def build_active_workspace_identity_payload(
    registry: dict[str, Any],
    current_instance_id: str,
) -> dict[str, Any] | None:
    active_instance_id = str(registry.get("active_workspace", "")).strip()
    if not active_instance_id:
        return None

    active_record = registry.get("workspaces", {}).get(active_instance_id, {})
    active_workspace_id = None
    if isinstance(active_record, dict):
        active_workspace_id = active_record.get("project_workspace_id") or None

    return {
        "instance_id": active_instance_id,
        "workspace_id": active_workspace_id,
        "is_current": active_instance_id == current_instance_id,
    }


def build_workspace_identity_payload(
    config: factory_workspace.WorkspaceRuntimeConfig,
    registry: dict[str, Any],
    *,
    snapshot: Any | None = None,
    active: bool | None = None,
) -> dict[str, Any]:
    runtime_topology = getattr(snapshot, "runtime_topology", {}) or {}
    runtime_mode = getattr(snapshot, "runtime_mode", config.runtime_mode)
    active_flag = (
        registry.get("active_workspace", "") == config.factory_instance_id
        if active is None
        else active
    )
    return {
        "workspace_id": config.project_workspace_id,
        "instance_id": config.factory_instance_id,
        "target": str(config.target_dir),
        "compose_project": config.compose_project_name,
        "runtime_mode": serialize_machine_readable_value(runtime_mode),
        "topology_mode": runtime_topology.get("mode", config.shared_service_mode),
        "active": active_flag,
        "active_workspace": build_active_workspace_identity_payload(
            registry,
            config.factory_instance_id,
        ),
    }


def build_service_diagnostics_payload(snapshot: Any) -> dict[str, dict[str, Any]]:
    services = getattr(snapshot, "services", {}) or {}
    diagnostics: dict[str, dict[str, Any]] = {}
    for service_name in sorted(services.keys()):
        service_record = services[service_name]
        published_ports = list(getattr(service_record, "published_ports", ()) or ())
        expected_port = getattr(service_record, "expected_port", None)
        diagnostics[service_name] = {
            "status": getattr(
                getattr(service_record, "status", None),
                "value",
                getattr(service_record, "status", ""),
            ),
            "docker_status": getattr(service_record, "docker_status", ""),
            "service_kind": getattr(
                getattr(service_record, "service_kind", None),
                "value",
                getattr(service_record, "service_kind", ""),
            ),
            "scope": getattr(
                getattr(service_record, "scope", None),
                "value",
                getattr(service_record, "scope", ""),
            ),
            "topology_mode": getattr(service_record, "topology_mode", ""),
            "workspace_owned": bool(getattr(service_record, "workspace_owned", False)),
            "runtime_identity": getattr(
                service_record,
                "runtime_identity",
                service_name,
            ),
            "workspace_server_name": getattr(
                service_record,
                "workspace_server_name",
                None,
            ),
            "expected_port": expected_port,
            "published_ports": published_ports,
            "port_match": (
                expected_port in published_ports if expected_port is not None else None
            ),
            "discovery_url": getattr(service_record, "discovery_url", ""),
            "probe_url": getattr(service_record, "probe_url", ""),
            "reason_codes": [
                getattr(reason_code, "value", str(reason_code))
                for reason_code in (getattr(service_record, "reason_codes", ()) or ())
            ],
            "details": list(getattr(service_record, "details", ()) or ()),
        }
    return diagnostics


def build_preflight_json_payload(
    report: dict[str, Any],
    registry: dict[str, Any],
    *,
    command: str,
    runtime_state: str | None = None,
    notices: Sequence[str] = (),
) -> dict[str, Any]:
    config = report["config"]
    snapshot = require_preflight_snapshot(report)
    readiness = report.get("readiness") or getattr(snapshot, "readiness", None)
    payload = {
        "command": command,
        "authority": "manager-backed-snapshot-readiness",
        "notices": list(notices),
        "workspace": build_workspace_identity_payload(
            config,
            registry,
            snapshot=snapshot,
        ),
        "runtime": {
            "runtime_state": runtime_state
            or resolve_status_runtime_state_from_snapshot(snapshot),
            "lifecycle_state": serialize_machine_readable_value(
                getattr(snapshot, "lifecycle_state", None)
            ),
            "persisted_runtime_state": getattr(
                snapshot,
                "persisted_runtime_state",
                "",
            ),
            "selection": serialize_machine_readable_value(
                getattr(snapshot, "selection", None)
            ),
            "recovery": serialize_machine_readable_value(
                getattr(snapshot, "recovery", None)
            ),
            "last_transition_at": getattr(snapshot, "last_transition_at", None),
            "last_transition_reason_codes": serialize_machine_readable_value(
                getattr(snapshot, "last_transition_reason_codes", ())
            ),
        },
        "preflight": {
            "status": report["status"],
            "recommended_action": report["recommended_action"],
            "reason_codes": list(report.get("reason_codes", [])),
            "issues": list(report.get("issues", [])),
            "blocking_services": list(report.get("blocking_services", [])),
            "readiness": serialize_machine_readable_value(readiness),
        },
        "diagnostics": {
            "runtime_topology": serialize_machine_readable_value(
                getattr(snapshot, "runtime_topology", {})
            ),
            "shared_mode_diagnostics": serialize_machine_readable_value(
                getattr(snapshot, "shared_mode_diagnostics", {})
            ),
            "workspace_urls": serialize_machine_readable_value(
                getattr(snapshot, "workspace_urls", {})
            ),
            "expected_workspace_urls": serialize_machine_readable_value(
                getattr(snapshot, "expected_workspace_urls", {})
                or config.mcp_server_urls
            ),
            "manifest_server_urls": serialize_machine_readable_value(
                getattr(snapshot, "manifest_server_urls", {})
            ),
            "manifest_health_urls": serialize_machine_readable_value(
                getattr(snapshot, "manifest_health_urls", {})
            ),
            "expected_service_ports": serialize_machine_readable_value(
                getattr(snapshot, "expected_service_ports", {})
            ),
        },
        "services": build_service_diagnostics_payload(snapshot),
    }
    return payload


def build_status_json_payload(
    config: factory_workspace.WorkspaceRuntimeConfig,
    registry: dict[str, Any],
    preflight: dict[str, Any],
    snapshot: Any,
    *,
    runtime_state: str,
    active: bool,
    installed_version: str,
    head_commit: str,
    lock_commit: str,
    needs_rebuild: bool,
    notices: Sequence[str] = (),
) -> dict[str, Any]:
    payload = build_preflight_json_payload(
        preflight,
        registry,
        command="status",
        runtime_state=runtime_state,
        notices=notices,
    )
    payload["workspace"]["active"] = active
    payload["workspace"]["port_index"] = config.port_index
    payload["runtime"].update(
        {
            "installed_version": installed_version,
            "factory_commit": head_commit,
            "lock_commit": lock_commit,
            "needs_rebuild": needs_rebuild,
        }
    )
    payload["diagnostics"]["effective_workspace_urls"] = (
        serialize_machine_readable_value(
            getattr(snapshot, "expected_workspace_urls", {}) or config.mcp_server_urls
        )
    )
    return payload


def build_status_preflight_error_payload(
    command: str,
    config: factory_workspace.WorkspaceRuntimeConfig,
    registry: dict[str, Any],
    exc: Exception,
    *,
    notices: Sequence[str] = (),
) -> dict[str, Any]:
    return {
        "command": command,
        "authority": "manager-backed-snapshot-readiness",
        "notices": list(notices),
        "workspace": build_workspace_identity_payload(config, registry),
        "runtime": {
            "runtime_state": "error",
            "lifecycle_state": None,
            "persisted_runtime_state": "",
            "selection": None,
            "recovery": None,
            "last_transition_at": None,
            "last_transition_reason_codes": [],
        },
        "preflight": {
            "status": "error",
            "recommended_action": "inspect-registry",
            "reason_codes": [],
            "issues": [str(exc)],
            "blocking_services": [],
            "readiness": None,
        },
        "diagnostics": {
            "error": str(exc),
            "runtime_topology": {},
            "shared_mode_diagnostics": {},
            "workspace_urls": {},
            "expected_workspace_urls": serialize_machine_readable_value(
                config.mcp_server_urls
            ),
            "manifest_server_urls": {},
            "manifest_health_urls": {},
            "expected_service_ports": {},
            "effective_workspace_urls": serialize_machine_readable_value(
                config.mcp_server_urls
            ),
        },
        "services": {},
    }


def print_json_output(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def resolve_status_runtime_state_from_snapshot(snapshot: Any) -> str:
    persisted_state = snapshot.persisted_runtime_state.strip() or "installed"

    if not snapshot.docker_available or snapshot.inventory_error:
        return persisted_state

    if snapshot.lifecycle_state == RuntimeLifecycleState.STARTING:
        return "starting"
    if snapshot.lifecycle_state == RuntimeLifecycleState.RUNNING:
        return "running"
    if snapshot.lifecycle_state == RuntimeLifecycleState.DEGRADED:
        return "degraded"
    if snapshot.lifecycle_state == RuntimeLifecycleState.SUSPENDED:
        return "suspended"
    if snapshot.lifecycle_state == RuntimeLifecycleState.STOPPED:
        if persisted_state in {"installed", "failed"}:
            return persisted_state
        return "stopped"
    return persisted_state


def build_preflight_report(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    workspace_file: str = DEFAULT_WORKSPACE_FILENAME,
) -> dict[str, Any]:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(
        repo_root, env_file=resolved_env_file, persist=False
    )
    manager = build_runtime_manager(workspace_file=workspace_file)
    snapshot = manager.build_snapshot(
        repo_root,
        env_file=resolved_env_file,
        workspace_file=workspace_file,
    )
    return build_preflight_report_from_snapshot(config, snapshot)


def require_preflight_snapshot(report: dict[str, Any]) -> Any:
    snapshot = report.get("snapshot") if isinstance(report, dict) else None
    if snapshot is None:
        raise RuntimeError(
            "Runtime preflight did not return a manager-backed snapshot."
        )
    return snapshot


def print_status_preflight_error(
    config: factory_workspace.WorkspaceRuntimeConfig,
    exc: Exception,
) -> None:
    print("preflight_status=error")
    print("recommended_action=inspect-registry")
    print("reason_codes=")
    print(f"preflight_error={exc}")
    for name, url in sorted(config.mcp_server_urls.items()):
        print(f"mcp.{name}={url}")


def print_preflight_report(report: dict[str, Any]) -> None:
    config = report["config"]
    runtime_topology = report.get("runtime_topology", {})
    shared_mode_diagnostics = report.get("shared_mode_diagnostics", {})
    print(f"workspace_id={config.project_workspace_id}")
    print(f"instance_id={config.factory_instance_id}")
    print(f"target={config.target_dir}")
    print(f"compose_project={config.compose_project_name}")
    print(f"runtime_mode={report.get('runtime_mode', config.runtime_mode)}")
    print(
        "topology_mode="
        f"{runtime_topology.get('mode', factory_workspace.PER_WORKSPACE_TOPOLOGY_MODE)}"
    )
    if isinstance(shared_mode_diagnostics, dict):
        print(
            "shared_mode_configured="
            f"{str(bool(shared_mode_diagnostics.get('shared_mode_configured'))).lower()}"
        )
        print(
            "shared_mode_status="
            f"{shared_mode_diagnostics.get('shared_mode_status', '')}"
        )
        print(
            "tenant_identity_mode="
            f"{shared_mode_diagnostics.get('tenant_identity_mode', '')}"
        )
        print(
            "tenant_identity_required="
            f"{str(bool(shared_mode_diagnostics.get('tenant_identity_required'))).lower()}"
        )
        print(
            "expected_tenant_identity="
            f"{shared_mode_diagnostics.get('expected_tenant_identity', '')}"
        )
        print(
            "tenant_identity_header="
            f"{shared_mode_diagnostics.get('tenant_identity_header', '')}"
        )
        print(
            "missing_tenant_remediation="
            f"{shared_mode_diagnostics.get('missing_tenant_remediation', '')}"
        )
        print(
            "tenant_mismatch_remediation="
            f"{shared_mode_diagnostics.get('tenant_mismatch_remediation', '')}"
        )
    print(f"preflight_status={report['status']}")
    print(f"recommended_action={report['recommended_action']}")
    print("reason_codes=" + ",".join(report.get("reason_codes", [])))
    print(f"issue_count={len(report['issues'])}")

    for service_name, service_topology in sorted(
        runtime_topology.get("services", {}).items()
    ):
        print(
            f"service.{service_name}.topology_mode={service_topology.get('topology_mode', '')}"
        )
        print(
            "service."
            f"{service_name}.workspace_owned={str(bool(service_topology.get('workspace_owned'))).lower()}"
        )
        print(
            f"service.{service_name}.launch_scope={service_topology.get('launch_scope', '')}"
        )
        print(
            f"service.{service_name}.discovery_url={service_topology.get('discovery_url', '')}"
        )

    for service_name in sorted(report["expected_service_ports"].keys()):
        service_entry = report["service_inventory"].get(service_name, {})
        published_ports = service_entry.get("published_ports", [])
        expected_port = report["expected_service_ports"][service_name]
        published_value = ",".join(str(port) for port in published_ports) or ""
        print(f"service.{service_name}.status={service_entry.get('status', '')}")
        print(f"service.{service_name}.image={service_entry.get('image', '')}")
        print(f"service.{service_name}.expected_port={expected_port}")
        print(f"service.{service_name}.published_ports={published_value}")
        print(
            f"service.{service_name}.port_match={str(expected_port in published_ports).lower()}"
        )

    for server_name, url in sorted(report["workspace_urls"].items()):
        print(f"workspace.mcp.{server_name}={url}")
    for server_name, url in sorted(report["manifest_server_urls"].items()):
        print(f"manifest.mcp.{server_name}={url}")

    for index, issue in enumerate(report["issues"], start=1):
        print(f"issue.{index}={issue}")


def preflight_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    workspace_file: str = DEFAULT_WORKSPACE_FILENAME,
    output_json: bool = False,
) -> int:
    try:
        report = build_preflight_report(
            repo_root,
            env_file=env_file,
            workspace_file=workspace_file,
        )
    except RuntimeError as exc:
        if not output_json:
            raise
        resolved_env_file = resolve_env_file(repo_root, env_file)
        config = sync_workspace_runtime(
            repo_root,
            env_file=resolved_env_file,
            persist=False,
        )
        print_json_output(
            build_status_preflight_error_payload(
                "preflight",
                config,
                factory_workspace.load_registry(),
                exc,
            )
        )
        return 1

    if output_json:
        print_json_output(
            build_preflight_json_payload(
                report,
                factory_workspace.load_registry(),
                command="preflight",
            )
        )
    else:
        print_preflight_report(report)
    return 0 if report["status"] == "ready" else 1


def infer_runtime_state_from_services(
    running_services: dict[str, str],
    *,
    expected_runtime_services: set[str] | None = None,
) -> str:
    """Infer effective runtime state from observed Docker service statuses."""
    if not running_services:
        return "stopped"

    required_services = {
        service_name: metadata
        for service_name, metadata in factory_workspace.RUNTIME_SERVICE_CONTRACT.items()
        if expected_runtime_services is None
        or service_name in expected_runtime_services
    }
    degraded = False

    for service_name, metadata in required_services.items():
        status = str(running_services.get(service_name, "")).strip()
        if not status:
            degraded = True
            continue

        lowered = status.lower()
        if "restarting" in lowered or "unhealthy" in lowered or "dead" in lowered:
            degraded = True
            continue
        if "up" not in lowered:
            degraded = True
            continue
        if metadata.get("require_healthy_status") and "healthy" not in lowered:
            degraded = True

    return "degraded" if degraded else "running"


def resolve_status_runtime_state(
    persisted_state: str,
    inferred_state: str,
    *,
    docker_state_available: bool,
) -> str:
    normalized_persisted = persisted_state.strip() or "installed"
    if not docker_state_available:
        return normalized_persisted
    if inferred_state == "suspended":
        return "suspended"
    if inferred_state == "stopped":
        if normalized_persisted in {"installed", "failed"}:
            return normalized_persisted
        return "stopped"
    return inferred_state


def resolve_target_dir_from_env(repo_root: Path, env_file: Path) -> Path:
    env_values = factory_workspace.parse_env_file(env_file)
    target_value = env_values.get("TARGET_WORKSPACE_PATH", "").strip()
    if target_value:
        return Path(target_value).expanduser().resolve()
    return repo_root.parents[1].resolve()


def read_factory_lock_commit(target_dir: Path) -> str:
    """Return the factory commit SHA recorded in .copilot/softwareFactoryVscode/lock.json, or ''."""
    lock_path = target_dir / ".copilot/softwareFactoryVscode/lock.json"
    try:
        data = json.loads(lock_path.read_text())
        return str(data.get("factory", {}).get("commit", "")).strip()
    except (Exception, json.JSONDecodeError, KeyError):
        import traceback

        traceback.print_exc()
        return ""


def get_factory_head_commit(factory_dir: Path) -> str:
    """Return the current git HEAD commit of the factory directory, or ''."""
    try:
        result = subprocess.run(
            ["git", "-C", str(factory_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        import traceback

        traceback.print_exc()
        return ""


def write_factory_lock_commit(target_dir: Path, factory_dir: Path) -> None:
    """Stamp the factory's current HEAD commit into .copilot/softwareFactoryVscode/lock.json."""
    commit = get_factory_head_commit(factory_dir)
    if not commit:
        return
    lock_path = target_dir / ".copilot/softwareFactoryVscode/lock.json"
    try:
        data = json.loads(lock_path.read_text()) if lock_path.exists() else {}
        data.setdefault("factory", {})["commit"] = commit
        lock_path.write_text(json.dumps(data, indent=4) + "\n")
    except (OSError, json.JSONDecodeError):
        pass  # non-fatal — status will show needs_rebuild=true until next build


def sync_workspace_runtime(
    repo_root: Path,
    *,
    env_file: Path,
    persist: bool = True,
) -> factory_workspace.WorkspaceRuntimeConfig:
    target_dir = resolve_target_dir_from_env(repo_root, env_file)
    config = factory_workspace.build_runtime_config(
        target_dir,
        factory_dir=repo_root,
    )
    registry = factory_workspace.load_registry()
    existing_record = registry.get("workspaces", {}).get(config.factory_instance_id, {})
    runtime_state = "installed"
    if isinstance(existing_record, dict):
        runtime_state = str(existing_record.get("runtime_state", "installed"))
    if persist:
        factory_workspace.sync_runtime_artifacts(
            config,
            runtime_state=runtime_state,
            active=None,
        )
    return config


def collect_unavailable_ports(
    config: factory_workspace.WorkspaceRuntimeConfig,
) -> list[str]:
    return [
        f"{key}={value}"
        for key, value in sorted(config.ports.items())
        if not factory_workspace.can_bind_port(value)
    ]


def ensure_ports_ready(config: factory_workspace.WorkspaceRuntimeConfig) -> None:
    try:
        running_services = collect_running_services(config.compose_project_name)
    except subprocess.CalledProcessError:
        running_services = {}
    if running_services:
        return
    if factory_workspace.ports_available(config.ports):
        return

    used_ports = collect_unavailable_ports(config)
    details = ", ".join(used_ports) if used_ports else "unknown ports"
    print(
        "⚠️ Workspace runtime ports still appear busy before start; proceeding because "
        "the local bind probe can false-positive while Docker is reconciling listeners: "
        + details
    )


def ensure_data_dirs_ready(config: factory_workspace.WorkspaceRuntimeConfig) -> None:
    factory_workspace.ensure_factory_data_dirs(config)


def start_stack(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    build: bool = True,
    wait: bool = True,
    wait_timeout: int = DEFAULT_WAIT_TIMEOUT,
    foreground: bool = False,
) -> Path:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(repo_root, env_file=resolved_env_file)
    topology_issues = factory_workspace.validate_runtime_topology(config)
    if topology_issues:
        details = "\n- ".join(topology_issues)
        raise RuntimeError(
            "Shared-service topology configuration is incomplete:\n- " f"{details}"
        )
    ensure_data_dirs_ready(config)
    ensure_ports_ready(config)
    if foreground:
        action = ["up"]
        if build:
            action.append("--build")
    else:
        action = ["up", "-d"]
        if build:
            action.append("--build")
        if wait:
            action.extend(["--wait", "--wait-timeout", str(wait_timeout)])
    if config.runtime_mode == factory_workspace.PRODUCTION_RUNTIME_MODE:
        action.extend(["--scale", "mock-llm-gateway=0"])
    if config.shared_service_mode == factory_workspace.SHARED_TOPOLOGY_MODE:
        for service_name in sorted(factory_workspace.PROMOTABLE_SHARED_SERVICES):
            action.extend(["--scale", f"{service_name}=0"])
    factory_workspace.update_runtime_state(config.factory_instance_id, "starting")
    if foreground:
        final_state = "stopped"
        try:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, "running"
            )
            run_compose_command(
                repo_root,
                build_compose_command(repo_root, resolved_env_file, action),
            )
        except subprocess.CalledProcessError:
            final_state = "failed"
            raise
        except KeyboardInterrupt:
            print("\nShutting down stack...")
        finally:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, final_state
            )
        return resolved_env_file
    else:
        try:
            run_compose_command(
                repo_root,
                build_compose_command(repo_root, resolved_env_file, action),
            )
        except subprocess.CalledProcessError:
            factory_workspace.update_runtime_state(config.factory_instance_id, "failed")
            raise
        if build:
            write_factory_lock_commit(config.target_dir, repo_root)
        try:
            running_services = collect_running_services(config.compose_project_name)
        except subprocess.CalledProcessError:
            running_services = {}
        inferred_state = infer_runtime_state_from_services(
            running_services,
            expected_runtime_services=factory_workspace.workspace_owned_runtime_services(
                config
            ),
        )
        if inferred_state == "stopped":
            inferred_state = "running"
        factory_workspace.update_runtime_state(
            config.factory_instance_id, inferred_state
        )
        return resolved_env_file


def stop_stack(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    remove_volumes: bool = False,
    preserve_runtime_state: bool = False,
) -> Path:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(repo_root, env_file=resolved_env_file)
    action = ["down", "--remove-orphans"]
    if remove_volumes:
        action.append("-v")

    try:
        run_compose_command(
            repo_root,
            build_compose_command(repo_root, resolved_env_file, action),
        )
    except subprocess.CalledProcessError:
        factory_workspace.update_runtime_state(config.factory_instance_id, "failed")
        print(
            "❌ Failed to stop workspace "
            f"`{config.project_workspace_id}` [{config.factory_instance_id}]. "
            "Runtime state marked as `failed` for operator visibility."
        )
        raise
    if not preserve_runtime_state:
        factory_workspace.update_runtime_state(config.factory_instance_id, "stopped")
    removal_effect = (
        "Removed containers and named volumes"
        if remove_volumes
        else "Removed containers and retained named volumes"
    )
    metadata_effect = (
        "preserved existing runtime-state metadata"
        if preserve_runtime_state
        else "retained generated runtime metadata and marked the workspace `stopped`"
    )
    print(
        "🛑 Stopped workspace "
        f"`{config.project_workspace_id}` [{config.factory_instance_id}]. "
        f"{removal_effect}, {metadata_effect}, and retained Docker images."
    )
    return resolved_env_file


def suspend_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    completed_tool_call_boundary: bool = False,
) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    manager = build_runtime_manager()
    snapshot = manager.suspend(
        repo_root,
        env_file=resolved_env_file,
        completed_tool_call_boundary=completed_tool_call_boundary,
    )
    recovery = getattr(snapshot, "recovery", None)
    print(f"workspace_id={snapshot.workspace_id}")
    print(f"instance_id={snapshot.instance_id}")
    print(f"runtime_state={snapshot.lifecycle_state.value}")
    if recovery is not None:
        print(f"recovery_classification={recovery.classification.value}")
        print(
            "completed_tool_call_boundary="
            f"{str(recovery.completed_tool_call_boundary).lower()}"
        )
    return 0


def resume_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    manager = build_runtime_manager()
    snapshot = manager.resume(
        repo_root,
        env_file=resolved_env_file,
    )
    readiness = getattr(snapshot, "readiness", None)
    recovery = getattr(snapshot, "recovery", None)
    print(f"workspace_id={snapshot.workspace_id}")
    print(f"instance_id={snapshot.instance_id}")
    print(f"runtime_state={snapshot.lifecycle_state.value}")
    if readiness is not None:
        print(f"preflight_status={readiness.status.value}")
        print(f"recommended_action={readiness.recommended_action.value}")
    if recovery is not None:
        print(f"recovery_classification={recovery.classification.value}")
        print(
            "completed_tool_call_boundary="
            f"{str(recovery.completed_tool_call_boundary).lower()}"
        )
    return 0


def backup_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    manager = build_runtime_manager()
    backup_result = manager.backup(
        repo_root,
        env_file=resolved_env_file,
    )
    print(f"workspace_id={backup_result['workspace_id']}")
    print(f"instance_id={backup_result['instance_id']}")
    print(f"runtime_state={backup_result['runtime_state']}")
    print(f"required_precondition={backup_result['required_precondition']}")
    print(f"bundle_created_at={backup_result['bundle_created_at']}")
    print(f"bundle_path={backup_result['bundle_path']}")
    print(f"manifest_path={backup_result['manifest_path']}")
    print(f"checksums_path={backup_result['checksums_path']}")
    print(f"captured_artifact_count={backup_result['captured_artifact_count']}")
    recovery_classification = str(
        backup_result.get("recovery_classification", "")
    ).strip()
    if recovery_classification:
        print(f"recovery_classification={recovery_classification}")
    print(
        "completed_tool_call_boundary="
        f"{str(bool(backup_result.get('completed_tool_call_boundary'))).lower()}"
    )
    return 0


def restore_workspace(
    repo_root: Path,
    *,
    bundle_path: Path,
    env_file: Path | None = None,
) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    manager = build_runtime_manager()
    restore_result = manager.restore(
        repo_root,
        bundle_path=bundle_path,
        env_file=resolved_env_file,
    )
    print(f"workspace_id={restore_result['workspace_id']}")
    print(f"instance_id={restore_result['instance_id']}")
    print(f"runtime_state={restore_result['runtime_state']}")
    print(f"bundle_path={restore_result['bundle_path']}")
    print(f"restored_artifact_count={restore_result['restored_artifact_count']}")
    preflight_status = str(restore_result.get("preflight_status", "")).strip()
    if preflight_status:
        print(f"preflight_status={preflight_status}")
    recommended_action = str(restore_result.get("recommended_action", "")).strip()
    if recommended_action:
        print(f"recommended_action={recommended_action}")
    recovery_classification = str(
        restore_result.get("recovery_classification", "")
    ).strip()
    if recovery_classification:
        print(f"recovery_classification={recovery_classification}")
    print(
        "completed_tool_call_boundary="
        f"{str(bool(restore_result.get('completed_tool_call_boundary'))).lower()}"
    )
    return 0


def cleanup_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
) -> int:
    manager = build_runtime_manager()
    return manager.cleanup(repo_root, env_file=env_file, trigger="cleanup")


def list_workspaces() -> int:
    try:
        res = factory_workspace.reconcile_registry()
    except RuntimeError as exc:
        print("❌ Registry reconciliation failed; lifecycle state may be inconsistent.")
        print(str(exc))
        return 1
    if res.get("stale_removed"):
        for stale_id in res["stale_removed"]:
            print(f"🧹 Removed stale registry record for: {stale_id}")
    if res.get("recovered_ids"):
        for recovered_id in res["recovered_ids"]:
            print(
                "♻️ Recovered registry identity from runtime metadata for: "
                f"{recovered_id}"
            )
    if res.get("rebuilt_manifest_ids"):
        for rebuilt_id in res["rebuilt_manifest_ids"]:
            print(
                "🛠️ Rebuilt missing runtime manifest from local workspace metadata for: "
                f"{rebuilt_id}"
            )
    registry = factory_workspace.load_registry()
    active_workspace = registry.get("active_workspace", "")
    for instance_id, record in sorted(registry.get("workspaces", {}).items()):
        marker = "*" if instance_id == active_workspace else " "
        print(
            f"{marker} {record.get('project_workspace_id', '')} "
            f"[{instance_id}] state={record.get('runtime_state', 'unknown')} "
            f"ports={record.get('port_index', '?')} path={record.get('target_workspace_path', '')}"
        )
    return 0


def status_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
    output_json: bool = False,
) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(
        repo_root, env_file=resolved_env_file, persist=False
    )
    registry = factory_workspace.load_registry()
    notices: list[str] = []
    record = registry.get("workspaces", {}).get(config.factory_instance_id)
    record_persisted = isinstance(record, dict) and bool(record)
    if not isinstance(record, dict) or not record:
        try:
            factory_workspace.refresh_registry_entry(config.target_dir)
        except FileNotFoundError as exc:
            message = (
                "Unable to resolve workspace registry record for "
                f"`{config.target_dir}`. Continuing with transient installed state."
            )
            if output_json:
                notices.extend([message, f"error={exc}"])
            else:
                print(f"⚠️ {message}")
                print(f"error={exc}")
            record = {"runtime_state": "installed"}
            record_persisted = False
        else:
            registry = factory_workspace.load_registry()
            record = registry.get("workspaces", {}).get(config.factory_instance_id)
            if not isinstance(record, dict) or not record:
                message = (
                    "Unable to recover workspace registry record for "
                    f"`{config.factory_instance_id}` after refresh. "
                    "Continuing with transient installed state."
                )
                if output_json:
                    notices.append(message)
                else:
                    print(f"⚠️ {message}")
                record = {"runtime_state": "installed"}
                record_persisted = False
            else:
                record_persisted = True
                message = (
                    "Recovered missing registry record for: "
                    f"{config.factory_instance_id}"
                )
                if output_json:
                    notices.append(message)
                else:
                    print(f"♻️ {message}")

    persisted_state = str(record.get("runtime_state", "installed"))
    try:
        preflight = build_preflight_report(repo_root, env_file=resolved_env_file)
        snapshot = require_preflight_snapshot(preflight)
    except RuntimeError as exc:
        if output_json:
            print_json_output(
                build_status_preflight_error_payload(
                    "status",
                    config,
                    registry,
                    exc,
                    notices=notices,
                )
            )
        else:
            print_status_preflight_error(config, exc)
        return 1

    runtime_state = resolve_status_runtime_state_from_snapshot(snapshot)

    if runtime_state != persisted_state and record_persisted:
        try:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, runtime_state
            )
        except KeyError:
            message = (
                "Workspace registry entry disappeared while updating runtime state "
                f"for `{config.factory_instance_id}`."
            )
            if output_json:
                print_json_output(
                    build_status_preflight_error_payload(
                        "status",
                        config,
                        registry,
                        RuntimeError(message),
                        notices=notices,
                    )
                )
            else:
                print(f"❌ {message}")
            return 1
        registry = factory_workspace.load_registry()
        record = registry.get("workspaces", {}).get(config.factory_instance_id, record)

    active = registry.get("active_workspace", "") == config.factory_instance_id
    lock_path = config.target_dir / ".copilot/softwareFactoryVscode/lock.json"
    lock_data = load_json(lock_path)
    release_data = lock_data.get("release") if isinstance(lock_data, dict) else {}
    release_data = release_data if isinstance(release_data, dict) else {}
    lock_commit = read_factory_lock_commit(config.target_dir)
    head_commit = get_factory_head_commit(config.factory_dir)
    needs_rebuild = bool(head_commit) and (
        not lock_commit or lock_commit != head_commit
    )
    if output_json:
        print_json_output(
            build_status_json_payload(
                config,
                registry,
                preflight,
                snapshot,
                runtime_state=runtime_state,
                active=active,
                installed_version=release_data.get(
                    "display_version",
                    lock_data.get("version", "unknown"),
                ),
                head_commit=head_commit,
                lock_commit=lock_commit,
                needs_rebuild=needs_rebuild,
                notices=notices,
            )
        )
        return 0

    print(f"workspace_id={config.project_workspace_id}")
    print(f"instance_id={config.factory_instance_id}")
    print(f"target={config.target_dir}")
    print(f"compose_project={config.compose_project_name}")
    print(f"topology_mode={config.shared_service_mode}")
    print(f"runtime_mode={getattr(snapshot, 'runtime_mode', config.runtime_mode)}")
    print(f"runtime_state={runtime_state}")
    print(f"active={str(active).lower()}")
    print(f"port_index={config.port_index}")
    print(
        "installed_version="
        f"{release_data.get('display_version', lock_data.get('version', 'unknown'))}"
    )
    print(f"factory_commit={head_commit}")
    print(f"lock_commit={lock_commit}")
    print(f"needs_rebuild={str(needs_rebuild).lower()}")
    print(f"preflight_status={preflight['status']}")
    print(f"recommended_action={preflight['recommended_action']}")
    print("reason_codes=" + ",".join(preflight.get("reason_codes", [])))
    recovery = getattr(snapshot, "recovery", None)
    if recovery is not None:
        print(f"recovery_classification={recovery.classification.value}")
        print(
            "completed_tool_call_boundary="
            f"{str(recovery.completed_tool_call_boundary).lower()}"
        )
        if recovery.last_trigger is not None:
            print(f"last_runtime_action={recovery.last_trigger.value}")
    selection = getattr(snapshot, "selection", None)
    if selection is not None:
        activity_lease = getattr(selection, "activity_lease", None)
        execution_lease = getattr(selection, "execution_lease", None)
        if activity_lease is not None:
            print(
                "activity_lease_present="
                f"{str(bool(getattr(activity_lease, 'present', False))).lower()}"
            )
        if execution_lease is not None:
            print(
                "execution_lease_present="
                f"{str(bool(getattr(execution_lease, 'present', False))).lower()}"
            )
    preflight_topology = preflight.get("runtime_topology", {})
    shared_mode_diagnostics = preflight.get("shared_mode_diagnostics", {})
    if isinstance(preflight_topology, dict):
        print(
            "preflight_topology_mode="
            f"{preflight_topology.get('mode', config.shared_service_mode)}"
        )
    if isinstance(shared_mode_diagnostics, dict):
        print(
            "shared_mode_configured="
            f"{str(bool(shared_mode_diagnostics.get('shared_mode_configured'))).lower()}"
        )
        print(
            "shared_mode_status="
            f"{shared_mode_diagnostics.get('shared_mode_status', '')}"
        )
        print(
            "tenant_identity_mode="
            f"{shared_mode_diagnostics.get('tenant_identity_mode', '')}"
        )
        print(
            "tenant_identity_required="
            f"{str(bool(shared_mode_diagnostics.get('tenant_identity_required'))).lower()}"
        )
        print(
            "expected_tenant_identity="
            f"{shared_mode_diagnostics.get('expected_tenant_identity', '')}"
        )
        print(
            "tenant_identity_header="
            f"{shared_mode_diagnostics.get('tenant_identity_header', '')}"
        )
    effective_workspace_urls = (
        snapshot.expected_workspace_urls
        if snapshot is not None and getattr(snapshot, "expected_workspace_urls", None)
        else config.mcp_server_urls
    )
    for name, url in sorted(effective_workspace_urls.items()):
        print(f"mcp.{name}={url}")
    return 0


def activate_workspace(repo_root: Path, *, env_file: Path | None = None) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(
        repo_root, env_file=resolved_env_file, persist=False
    )
    registry = factory_workspace.load_registry()
    existing_record = registry.get("workspaces", {}).get(config.factory_instance_id, {})
    runtime_state = (
        str(existing_record.get("runtime_state", "installed"))
        if isinstance(existing_record, dict)
        else "installed"
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state=runtime_state,
        active=None,
    )
    factory_workspace.set_active_workspace(config.factory_instance_id)
    print(
        f"Activated workspace `{config.project_workspace_id}` [{config.factory_instance_id}]"
    )
    return 0


def deactivate_workspace(repo_root: Path, *, env_file: Path | None = None) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(
        repo_root, env_file=resolved_env_file, persist=False
    )
    factory_workspace.clear_active_workspace(config.factory_instance_id)
    print(
        f"Deactivated workspace `{config.project_workspace_id}` [{config.factory_instance_id}]"
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Canonical Software Factory runtime lifecycle helper. Supported stop, "
            "cleanup, backup, and restore paths follow the documented manager-backed "
            "lifecycle contract and do not prune Docker images."
        )
    )
    parser.add_argument(
        "command",
        choices=[
            "start",
            "stop",
            "suspend",
            "resume",
            "backup",
            "restore",
            "list",
            "status",
            "preflight",
            "activate",
            "deactivate",
            "cleanup",
        ],
        help="Workspace runtime lifecycle command.",
    )
    parser.add_argument(
        "--repo-root",
        default=str(SCRIPT_REPO_ROOT),
        help="Factory repository root containing the compose/ directory.",
    )
    parser.add_argument(
        "--env-file",
        default="",
        help=(
            "Optional explicit .factory.env path. Defaults to repo-root/.factory.env, "
            "or when running from the source checkout falls back to the companion "
            "installed-workspace env at `<target>/.copilot/softwareFactoryVscode/.factory.env` "
            "when present."
        ),
    )
    parser.add_argument(
        "--workspace-file",
        default=DEFAULT_WORKSPACE_FILENAME,
        help=(
            "Workspace filename used to validate generated MCP endpoint alignment "
            f"(default: {DEFAULT_WORKSPACE_FILENAME})."
        ),
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help=(
            "Build images while starting the stack (otherwise reuse existing "
            "retained images when available)."
        ),
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Start without Docker Compose health-aware waiting.",
    )
    parser.add_argument(
        "--wait-timeout",
        type=int,
        default=DEFAULT_WAIT_TIMEOUT,
        help=f"Compose wait timeout in seconds (default: {DEFAULT_WAIT_TIMEOUT}).",
    )
    parser.add_argument(
        "--remove-volumes",
        action="store_true",
        help=(
            "Also remove named volumes while stopping the stack; Docker images "
            "are still retained."
        ),
    )
    parser.add_argument(
        "--preserve-runtime-state",
        action="store_true",
        help=(
            "When stopping for refresh/update flows, keep existing runtime_state metadata "
            "instead of demoting to `stopped`."
        ),
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="Start attached in the foreground (without -d or --wait).",
    )
    parser.add_argument(
        "--completed-tool-call-boundary",
        action="store_true",
        help=(
            "When suspending, record that the current prompt/session is paused on a "
            "completed tool-call boundary so resume remains classified as safe."
        ),
    )
    parser.add_argument(
        "--bundle-path",
        default="",
        help=(
            "Backup bundle directory used by `restore`. This should point to the "
            f"directory containing `{factory_workspace.RUNTIME_MANIFEST_FILENAME}`'s "
            "paired backup metadata files."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON for `status` and `preflight`.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    env_file = Path(args.env_file).expanduser().resolve() if args.env_file else None

    if args.command == "start":
        start_stack(
            repo_root,
            env_file=env_file,
            build=args.build,
            wait=not args.no_wait,
            wait_timeout=args.wait_timeout,
            foreground=args.foreground,
        )
    elif args.command == "stop":
        stop_stack(
            repo_root,
            env_file=env_file,
            remove_volumes=args.remove_volumes,
            preserve_runtime_state=args.preserve_runtime_state,
        )
    elif args.command == "suspend":
        return suspend_workspace(
            repo_root,
            env_file=env_file,
            completed_tool_call_boundary=args.completed_tool_call_boundary,
        )
    elif args.command == "resume":
        return resume_workspace(
            repo_root,
            env_file=env_file,
        )
    elif args.command == "backup":
        return backup_workspace(
            repo_root,
            env_file=env_file,
        )
    elif args.command == "restore":
        bundle_path_text = str(args.bundle_path).strip()
        if not bundle_path_text:
            raise SystemExit("`restore` requires --bundle-path <backup-bundle-dir>.")
        return restore_workspace(
            repo_root,
            bundle_path=Path(bundle_path_text).expanduser().resolve(),
            env_file=env_file,
        )
    elif args.command == "cleanup":
        return cleanup_workspace(
            repo_root,
            env_file=env_file,
        )
    elif args.command == "list":
        return list_workspaces()
    elif args.command == "status":
        return status_workspace(
            repo_root,
            env_file=env_file,
            output_json=args.json,
        )
    elif args.command == "preflight":
        return preflight_workspace(
            repo_root,
            env_file=env_file,
            workspace_file=args.workspace_file,
            output_json=args.json,
        )
    elif args.command == "activate":
        return activate_workspace(repo_root, env_file=env_file)
    elif args.json:
        raise SystemExit("`--json` is supported only for `status` and `preflight`.")
    else:
        return deactivate_workspace(repo_root, env_file=env_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
