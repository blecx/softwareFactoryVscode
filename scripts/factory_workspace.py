#!/usr/bin/env python3
"""Shared helpers for workspace-scoped Software Factory runtime metadata."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import factory_release

FACTORY_DIRNAME = ".copilot/softwareFactoryVscode"
TMP_SUBPATH = Path(FACTORY_DIRNAME) / ".tmp"
RUNTIME_MANIFEST_FILENAME = "runtime-manifest.json"
REGISTRY_FILENAME = "workspace-registry.json"
REGISTRY_VERSION = 1
DEFAULT_WORKSPACE_FILENAME = "software-factory.code-workspace"
PORT_BLOCK_STRIDE = 100

PORT_LAYOUT: dict[str, int] = {
    "PORT_CONTEXT7": 3010,
    "PORT_BASH": 3011,
    "PORT_FS": 3012,
    "PORT_GIT": 3013,
    "PORT_SEARCH": 3014,
    "PORT_TEST": 3015,
    "PORT_COMPOSE": 3016,
    "PORT_DOCS": 3017,
    "PORT_GITHUB": 3018,
    "MEMORY_MCP_PORT": 3030,
    "AGENT_BUS_PORT": 3031,
    "APPROVAL_GATE_PORT": 8001,
    "PORT_TUI": 9090,
}

MCP_SERVER_PORT_KEYS: dict[str, str] = {
    "context7": "PORT_CONTEXT7",
    "bashGateway": "PORT_BASH",
    "git": "PORT_FS",
    "search": "PORT_GIT",
    "filesystem": "PORT_SEARCH",
    "dockerCompose": "PORT_COMPOSE",
    "testRunner": "PORT_TEST",
    "offlineDocs": "PORT_DOCS",
    "githubOps": "PORT_GITHUB",
}

RUNTIME_SERVICE_CONTRACT: dict[str, dict[str, Any]] = {
    "mock-llm-gateway": {
        "port_key": "PORT_TUI",
        "health_path": "/admin/mocks",
        "require_healthy_status": True,
        "allow_http_error": False,
        "scope": "candidate-shared",
    },
    "mcp-memory": {
        "port_key": "MEMORY_MCP_PORT",
        "health_path": "/mcp",
        "require_healthy_status": True,
        "allow_http_error": True,
        "scope": "candidate-shared",
    },
    "mcp-agent-bus": {
        "port_key": "AGENT_BUS_PORT",
        "health_path": "/mcp",
        "require_healthy_status": True,
        "allow_http_error": True,
        "scope": "candidate-shared",
    },
    "approval-gate": {
        "port_key": "APPROVAL_GATE_PORT",
        "health_path": "/health",
        "require_healthy_status": True,
        "allow_http_error": False,
        "scope": "candidate-shared",
    },
    "agent-worker": {
        "port_key": "",
        "health_path": "",
        "require_healthy_status": True,
        "allow_http_error": False,
        "scope": "candidate-shared",
    },
}

HEALTH_ENDPOINTS: dict[str, tuple[str, str]] = {
    service_name: (str(metadata["port_key"]), str(metadata["health_path"]))
    for service_name, metadata in RUNTIME_SERVICE_CONTRACT.items()
    if metadata.get("port_key") and metadata.get("health_path")
}

WORKSPACE_SCOPED_SERVICES = {
    "context7",
    "bashGateway",
    "git",
    "search",
    "filesystem",
    "dockerCompose",
    "testRunner",
    "offlineDocs",
    "githubOps",
    "agent-worker",
}

CANDIDATE_SHARED_SERVICES = {
    service_name
    for service_name, metadata in RUNTIME_SERVICE_CONTRACT.items()
    if metadata.get("scope") == "candidate-shared"
}

MANAGED_ENV_KEYS = [
    "TARGET_WORKSPACE_PATH",
    "PROJECT_WORKSPACE_ID",
    "COMPOSE_PROJECT_NAME",
    "FACTORY_DIR",
    "FACTORY_DATA_DIR",
    "FACTORY_INSTANCE_ID",
    "FACTORY_PORT_INDEX",
    *PORT_LAYOUT.keys(),
]


@dataclass(frozen=True)
class WorkspaceRuntimeConfig:
    target_dir: Path
    factory_dir: Path
    workspace_file: str
    workspace_file_path: Path
    runtime_manifest_path: Path
    project_workspace_id: str
    factory_instance_id: str
    compose_project_name: str
    port_index: int
    env_values: dict[str, str]
    ports: dict[str, int]
    mcp_server_urls: dict[str, str]
    workspace_settings: dict[str, Any]


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False
    ) as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temp_path = Path(handle.name)
    temp_path.replace(path)


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def slugify_identifier(value: str) -> str:
    lowered = value.strip().lower()
    slug = "".join(ch if ch.isalnum() else "-" for ch in lowered)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "workspace"


def default_registry_path() -> Path:
    override = os.environ.get("SOFTWARE_FACTORY_REGISTRY_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()

    xdg_state_home = os.environ.get("XDG_STATE_HOME", "").strip()
    if xdg_state_home:
        base_dir = Path(xdg_state_home).expanduser().resolve()
    else:
        base_dir = (Path.home() / ".local" / "state").resolve()

    return base_dir / "softwareFactoryVscode" / REGISTRY_FILENAME


def load_registry(registry_path: Path | None = None) -> dict[str, Any]:
    path = registry_path or default_registry_path()
    if not path.exists():
        return {
            "version": REGISTRY_VERSION,
            "active_workspace": "",
            "workspaces": {},
            "updated_at": utc_now_iso(),
        }

    data = load_json(path)
    if not isinstance(data, dict):
        return {
            "version": REGISTRY_VERSION,
            "active_workspace": "",
            "workspaces": {},
            "updated_at": utc_now_iso(),
        }

    data.setdefault("version", REGISTRY_VERSION)
    data.setdefault("active_workspace", "")
    data.setdefault("workspaces", {})
    data.setdefault("updated_at", utc_now_iso())
    if not isinstance(data["workspaces"], dict):
        data["workspaces"] = {}
    return data


def save_registry(data: dict[str, Any], registry_path: Path | None = None) -> Path:
    path = registry_path or default_registry_path()
    data = dict(data)
    data["version"] = REGISTRY_VERSION
    data["updated_at"] = utc_now_iso()
    write_json_atomic(path, data)
    return path


def build_port_values(port_index: int) -> dict[str, int]:
    offset = port_index * PORT_BLOCK_STRIDE
    return {key: default + offset for key, default in PORT_LAYOUT.items()}


def ports_conflict(left: dict[str, int], right: dict[str, int]) -> bool:
    return bool(set(left.values()) & set(right.values()))


def can_bind_port(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def ports_available(ports: dict[str, int]) -> bool:
    return all(can_bind_port(port) for port in ports.values())


def derive_instance_id(target_dir: Path) -> str:
    digest = hashlib.sha1(str(target_dir).encode("utf-8")).hexdigest()[:12]
    return f"factory-{digest}"


def build_mcp_server_urls(ports: dict[str, int]) -> dict[str, str]:
    return {
        server_name: f"http://127.0.0.1:{ports[port_key]}/mcp"
        for server_name, port_key in MCP_SERVER_PORT_KEYS.items()
    }


def build_health_urls(ports: dict[str, int]) -> dict[str, str]:
    return {
        service_name: f"http://127.0.0.1:{ports[port_key]}{path}"
        for service_name, (port_key, path) in HEALTH_ENDPOINTS.items()
    }


def load_canonical_workspace_settings(factory_dir: Path) -> dict[str, Any]:
    config_path = factory_dir / ".copilot" / "config" / "vscode-agent-settings.json"
    config = load_json(config_path)
    workspace_settings = config.get("workspace", {})
    return workspace_settings if isinstance(workspace_settings, dict) else {}


def build_effective_workspace_settings(
    factory_dir: Path,
    ports: dict[str, int],
) -> dict[str, Any]:
    settings = json.loads(json.dumps(load_canonical_workspace_settings(factory_dir)))
    mcp = settings.get("mcp")
    if not isinstance(mcp, dict):
        return settings
    servers = mcp.get("servers")
    if not isinstance(servers, dict):
        return settings
    urls = build_mcp_server_urls(ports)
    for server_name, server_config in servers.items():
        if server_name not in urls or not isinstance(server_config, dict):
            continue
        server_config["url"] = urls[server_name]
    return settings


def find_available_port_index(
    *,
    registry_path: Path | None = None,
    preferred_index: int | None = None,
    exclude_instance_id: str = "",
    max_port_index: int = 200,
) -> int:
    registry = load_registry(registry_path)
    used_indices = {
        int(record.get("port_index", -1))
        for instance_id, record in registry.get("workspaces", {}).items()
        if instance_id != exclude_instance_id and isinstance(record, dict)
    }
    used_port_sets = [
        {
            key: int(value)
            for key, value in record.get("ports", {}).items()
            if key in PORT_LAYOUT
        }
        for instance_id, record in registry.get("workspaces", {}).items()
        if instance_id != exclude_instance_id and isinstance(record, dict)
    ]

    candidates: list[int] = []
    if preferred_index is not None:
        candidates.append(preferred_index)
    candidates.extend(
        index for index in range(max_port_index) if index != preferred_index
    )

    for index in candidates:
        if index in used_indices:
            continue
        ports = build_port_values(index)
        if any(ports_conflict(ports, used_ports) for used_ports in used_port_sets):
            continue
        if ports_available(ports):
            return index
    raise RuntimeError(
        "Unable to allocate a free workspace port block. "
        f"Checked {max_port_index} blocks ({PORT_BLOCK_STRIDE} ports each). "
        "Try cleaning stale registry entries with `factory_stack.py list`/`cleanup`, "
        "or free conflicting local ports."
    )


def assert_ports_do_not_conflict(
    ports: dict[str, int],
    *,
    registry_path: Path | None = None,
    exclude_instance_id: str = "",
) -> None:
    registry = load_registry(registry_path)
    for instance_id, record in registry.get("workspaces", {}).items():
        if instance_id == exclude_instance_id or not isinstance(record, dict):
            continue
        record_ports = {
            key: int(value)
            for key, value in record.get("ports", {}).items()
            if key in PORT_LAYOUT
        }
        if record_ports and ports_conflict(ports, record_ports):
            raise RuntimeError(
                "Workspace runtime ports conflict with registered workspace "
                f"`{instance_id}`."
            )


def build_runtime_config(
    target_dir: Path,
    *,
    factory_dir: Path | None = None,
    workspace_file: str = DEFAULT_WORKSPACE_FILENAME,
    registry_path: Path | None = None,
) -> WorkspaceRuntimeConfig:
    resolved_target = target_dir.expanduser().resolve()
    resolved_factory = (
        factory_dir.expanduser().resolve()
        if factory_dir is not None
        else (resolved_target / FACTORY_DIRNAME).resolve()
    )
    env_path = resolved_target / FACTORY_DIRNAME / ".factory.env"
    manifest_path = resolved_target / TMP_SUBPATH / RUNTIME_MANIFEST_FILENAME
    existing_env = parse_env_file(env_path)
    existing_manifest = load_json(manifest_path)

    project_workspace_id = existing_env.get(
        "PROJECT_WORKSPACE_ID",
        existing_manifest.get(
            "project_workspace_id", slugify_identifier(resolved_target.name)
        ),
    )
    project_workspace_id = slugify_identifier(project_workspace_id)

    factory_instance_id = existing_env.get(
        "FACTORY_INSTANCE_ID",
        existing_manifest.get(
            "factory_instance_id", derive_instance_id(resolved_target)
        ),
    )

    compose_project_name = existing_env.get(
        "COMPOSE_PROJECT_NAME",
        existing_manifest.get(
            "compose_project_name", f"factory_{project_workspace_id}"
        ),
    )

    preferred_index: int | None = None
    raw_index = existing_env.get(
        "FACTORY_PORT_INDEX",
        str(existing_manifest.get("port_index", "")).strip(),
    ).strip()
    if raw_index:
        try:
            preferred_index = int(raw_index)
        except ValueError:
            preferred_index = None

    existing_record: dict[str, Any] = {}
    if preferred_index is None:
        registry = load_registry(registry_path)
        existing_record = registry.get("workspaces", {}).get(factory_instance_id, {})
        if isinstance(existing_record, dict):
            existing_index = existing_record.get("port_index")
            if isinstance(existing_index, int):
                preferred_index = existing_index
    else:
        registry = load_registry(registry_path)
        existing_record = registry.get("workspaces", {}).get(factory_instance_id, {})
        if not isinstance(existing_record, dict):
            existing_record = {}

    persisted_ports: dict[str, int] = {}
    manifest_ports = existing_manifest.get("ports", {})
    if isinstance(manifest_ports, dict):
        for key, value in manifest_ports.items():
            if key not in PORT_LAYOUT:
                continue
            try:
                persisted_ports[key] = int(value)
            except (TypeError, ValueError):
                continue

    raw_record_ports = existing_record.get("ports", {})
    if isinstance(raw_record_ports, dict):
        for key, value in raw_record_ports.items():
            if key not in PORT_LAYOUT:
                continue
            try:
                persisted_ports.setdefault(key, int(value))
            except (TypeError, ValueError):
                continue

    for key in PORT_LAYOUT:
        raw_value = existing_env.get(key, "").strip()
        if not raw_value:
            continue
        try:
            persisted_ports[key] = int(raw_value)
        except ValueError:
            continue

    if persisted_ports:
        port_index = preferred_index if preferred_index is not None else 0
        ports = {
            **build_port_values(port_index),
            **persisted_ports,
        }
    else:
        port_index = find_available_port_index(
            registry_path=registry_path,
            preferred_index=preferred_index if preferred_index is not None else 0,
            exclude_instance_id=factory_instance_id,
        )
        ports = build_port_values(port_index)

    assert_ports_do_not_conflict(
        ports,
        registry_path=registry_path,
        exclude_instance_id=factory_instance_id,
    )

    managed_env = {
        "TARGET_WORKSPACE_PATH": str(resolved_target),
        "PROJECT_WORKSPACE_ID": project_workspace_id,
        "COMPOSE_PROJECT_NAME": compose_project_name,
        "FACTORY_DIR": str(resolved_factory),
        "FACTORY_DATA_DIR": existing_env.get(
            "FACTORY_DATA_DIR", str(resolved_factory / "data")
        ),
        "FACTORY_INSTANCE_ID": factory_instance_id,
        "FACTORY_PORT_INDEX": str(port_index),
        **{key: str(value) for key, value in ports.items()},
    }
    if "CONTEXT7_API_KEY" in existing_env:
        managed_env["CONTEXT7_API_KEY"] = existing_env["CONTEXT7_API_KEY"]
    else:
        managed_env["CONTEXT7_API_KEY"] = ""

    extra_env = {
        key: value
        for key, value in existing_env.items()
        if key not in managed_env and key not in MANAGED_ENV_KEYS
    }
    env_values = {**managed_env, **extra_env}

    workspace_file_path = (
        Path(workspace_file).expanduser().resolve()
        if Path(workspace_file).is_absolute()
        else (resolved_target / workspace_file).resolve()
    )
    workspace_settings = build_effective_workspace_settings(resolved_factory, ports)

    return WorkspaceRuntimeConfig(
        target_dir=resolved_target,
        factory_dir=resolved_factory,
        workspace_file=workspace_file,
        workspace_file_path=workspace_file_path,
        runtime_manifest_path=manifest_path,
        project_workspace_id=project_workspace_id,
        factory_instance_id=factory_instance_id,
        compose_project_name=compose_project_name,
        port_index=port_index,
        env_values=env_values,
        ports=ports,
        mcp_server_urls=build_mcp_server_urls(ports),
        workspace_settings=workspace_settings,
    )


def build_runtime_manifest(config: WorkspaceRuntimeConfig) -> dict[str, Any]:
    health_urls = build_health_urls(config.ports)
    release_metadata = factory_release.build_release_metadata(
        config.factory_dir,
        repo_url=factory_release.git_output(
            config.factory_dir, ["remote", "get-url", "origin"]
        ),
        source_ref=factory_release.current_branch(config.factory_dir),
    )
    factory_version = release_metadata["version_core"]

    return {
        "version": REGISTRY_VERSION,
        "generated_at": utc_now_iso(),
        "target_workspace_path": str(config.target_dir),
        "factory_dir": str(config.factory_dir),
        "workspace_file": config.workspace_file,
        "workspace_file_path": str(config.workspace_file_path),
        "project_workspace_id": config.project_workspace_id,
        "factory_instance_id": config.factory_instance_id,
        "compose_project_name": config.compose_project_name,
        "port_index": config.port_index,
        "ports": config.ports,
        "factory_version": factory_version,
        "factory_display_version": release_metadata["display_version"],
        "factory_release": release_metadata,
        "mcp_servers": {
            name: {
                "url": url,
                "scope": (
                    "workspace-scoped"
                    if name in WORKSPACE_SCOPED_SERVICES
                    else "candidate-shared"
                ),
            }
            for name, url in config.mcp_server_urls.items()
        },
        "runtime_health": {
            service_name: {
                "url": url,
                "scope": (
                    "candidate-shared"
                    if service_name in CANDIDATE_SHARED_SERVICES
                    else "workspace-scoped"
                ),
            }
            for service_name, url in health_urls.items()
        },
    }


def ensure_factory_data_dirs(config: WorkspaceRuntimeConfig) -> None:
    """Ensure bind-mounted runtime data directories exist for this workspace."""

    data_dir_value = str(config.env_values.get("FACTORY_DATA_DIR", "")).strip()
    if not data_dir_value:
        return

    base_dir = Path(data_dir_value).expanduser().resolve()
    for subdir in ("memory", "bus"):
        (base_dir / subdir / config.factory_instance_id).mkdir(
            parents=True,
            exist_ok=True,
        )


def sync_runtime_artifacts(
    config: WorkspaceRuntimeConfig,
    *,
    registry_path: Path | None = None,
    runtime_state: str = "installed",
    active: bool | None = None,
    write_env: bool = True,
) -> dict[str, Any]:
    config.target_dir.joinpath(TMP_SUBPATH).mkdir(parents=True, exist_ok=True)
    if write_env:
        (config.target_dir / FACTORY_DIRNAME).mkdir(parents=True, exist_ok=True)
    (config.target_dir / FACTORY_DIRNAME).mkdir(parents=True, exist_ok=True)
    ensure_factory_data_dirs(config)
    write_env_file(
        config.target_dir / FACTORY_DIRNAME / ".factory.env", config.env_values
    )

    manifest = build_runtime_manifest(config)
    write_json_atomic(config.runtime_manifest_path, manifest)
    upsert_workspace_record(
        manifest,
        registry_path=registry_path,
        runtime_state=runtime_state,
        active=active,
    )
    return manifest


def upsert_workspace_record(
    manifest: dict[str, Any],
    *,
    registry_path: Path | None = None,
    runtime_state: str = "installed",
    active: bool | None = None,
) -> Path:
    registry = load_registry(registry_path)
    instance_id = str(manifest.get("factory_instance_id", "")).strip()
    if not instance_id:
        raise ValueError("Runtime manifest is missing factory_instance_id.")

    existing = registry["workspaces"].get(instance_id, {})
    installed_at = (
        existing.get("installed_at", utc_now_iso())
        if isinstance(existing, dict)
        else utc_now_iso()
    )
    record = {
        "factory_instance_id": instance_id,
        "project_workspace_id": manifest.get("project_workspace_id", ""),
        "target_workspace_path": manifest.get("target_workspace_path", ""),
        "factory_dir": manifest.get("factory_dir", ""),
        "workspace_file_path": manifest.get("workspace_file_path", ""),
        "compose_project_name": manifest.get("compose_project_name", ""),
        "port_index": manifest.get("port_index", 0),
        "ports": manifest.get("ports", {}),
        "factory_version": manifest.get("factory_version", "unknown"),
        "factory_display_version": manifest.get("factory_display_version", ""),
        "factory_commit": (
            manifest.get("factory_release", {}).get("commit_sha", "")
            if isinstance(manifest.get("factory_release"), dict)
            else ""
        ),
        "runtime_state": runtime_state,
        "installed_at": installed_at,
        "last_activated_at": (
            existing.get("last_activated_at")
            if existing.get("last_activated_at")
            else (utc_now_iso() if active else None)
        ),
        "updated_at": utc_now_iso(),
    }
    registry["workspaces"][instance_id] = record

    if active is True:
        registry["active_workspace"] = instance_id
    elif active is False and registry.get("active_workspace") == instance_id:
        registry["active_workspace"] = ""

    return save_registry(registry, registry_path)


def set_active_workspace(
    instance_id: str | None,
    *,
    registry_path: Path | None = None,
) -> Path:
    registry = load_registry(registry_path)
    registry["active_workspace"] = instance_id or ""
    if instance_id and instance_id in registry.get("workspaces", {}):
        registry["workspaces"][instance_id]["last_activated_at"] = utc_now_iso()
        registry["workspaces"][instance_id]["updated_at"] = utc_now_iso()
    return save_registry(registry, registry_path)


def clear_active_workspace(
    instance_id: str,
    *,
    registry_path: Path | None = None,
) -> Path:
    registry = load_registry(registry_path)
    if registry.get("active_workspace") == instance_id:
        registry["active_workspace"] = ""
    return save_registry(registry, registry_path)


def update_runtime_state(
    instance_id: str,
    runtime_state: str,
    *,
    registry_path: Path | None = None,
) -> Path:
    registry = load_registry(registry_path)
    record = registry.get("workspaces", {}).get(instance_id)
    if not isinstance(record, dict):
        raise KeyError(f"Workspace `{instance_id}` is not present in the registry.")
    record["runtime_state"] = runtime_state
    record["updated_at"] = utc_now_iso()
    registry["workspaces"][instance_id] = record
    return save_registry(registry, registry_path)


def is_ephemeral_workspace_path(target_dir: Path) -> bool:
    """Return True for temporary pytest-generated workspace paths.

    These records are useful transiently during tests but add long-term noise
    when persisted in the operator registry.
    """
    target = str(target_dir)
    return "/pytest-of-" in target or "/pytest-" in target


def reconcile_registry(*, registry_path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(registry_path)
    workspaces = registry.get("workspaces", {})
    active_workspace = registry.get("active_workspace", "")
    stale_ids = []
    for iid, record in workspaces.items():
        if not isinstance(record, dict):
            stale_ids.append(iid)
            continue
        try:
            target_dir = Path(record.get("target_workspace_path", ""))
            if not target_dir.exists() or not target_dir.is_dir():
                stale_ids.append(iid)
                continue
            if iid != active_workspace and is_ephemeral_workspace_path(target_dir):
                stale_ids.append(iid)
                continue
            manifest_path = target_dir / TMP_SUBPATH / RUNTIME_MANIFEST_FILENAME
            if not manifest_path.exists():
                stale_ids.append(iid)
                continue
        except Exception:
            stale_ids.append(iid)

    for iid in stale_ids:
        del registry["workspaces"][iid]
        if registry.get("active_workspace") == iid:
            registry["active_workspace"] = ""

    if stale_ids:
        save_registry(registry, registry_path)

    return {"stale_removed": stale_ids, "remaining": len(registry["workspaces"])}


def refresh_registry_entry(
    target_dir: Path, *, registry_path: Path | None = None
) -> None:
    manifest_path = target_dir / TMP_SUBPATH / RUNTIME_MANIFEST_FILENAME
    if manifest_path.exists():
        manifest = load_json(manifest_path)
        if "factory_instance_id" in manifest:
            upsert_workspace_record(manifest, registry_path=registry_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Factory Workspace Registry CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    parser_list = subparsers.add_parser("list", help="List workspaces")
    parser_reconcile = subparsers.add_parser(
        "reconcile", help="Clean up stale registry records"
    )
    parser_refresh = subparsers.add_parser(
        "refresh", help="Refresh a workspace in the registry"
    )
    parser_refresh.add_argument(
        "target_dir", type=Path, help="Path to workspace target dir"
    )

    args = parser.parse_args()

    if args.command == "list":
        reg = load_registry()
        print(json.dumps(reg, indent=2))
    elif args.command == "reconcile":
        res = reconcile_registry()
        print(json.dumps(res, indent=2))
    elif args.command == "refresh":
        refresh_registry_entry(args.target_dir)
        print(f"Refreshed {args.target_dir}")
    else:
        parser.print_help()
