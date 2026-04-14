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

import factory_workspace

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
    expected_ports = {
        service_name: config.ports[metadata["port_key"]]
        for service_name, metadata in factory_workspace.RUNTIME_SERVICE_CONTRACT.items()
        if metadata.get("port_key")
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
    runtime_manifest = factory_workspace.load_json(config.runtime_manifest_path)
    workspace_urls = load_workspace_server_urls(config.target_dir, workspace_file)
    manifest_server_urls = {
        name: str(data.get("url", ""))
        for name, data in runtime_manifest.get("mcp_servers", {}).items()
        if isinstance(data, dict)
    }
    manifest_health_urls = {
        name: str(data.get("url", ""))
        for name, data in runtime_manifest.get("runtime_health", {}).items()
        if isinstance(data, dict)
    }

    expected_workspace_urls = config.mcp_server_urls
    expected_health_urls = factory_workspace.build_health_urls(config.ports)
    expected_service_ports = build_expected_service_ports(config)

    alignment_issues: list[str] = []
    for server_name, expected_url in sorted(expected_workspace_urls.items()):
        workspace_url = workspace_urls.get(server_name, "")
        if workspace_url != expected_url:
            alignment_issues.append(
                "Generated workspace MCP URL drift detected for "
                f"`{server_name}` (expected `{expected_url}`, found `{workspace_url or 'missing'}`)."
            )
        manifest_url = manifest_server_urls.get(server_name, "")
        if manifest_url != expected_url:
            alignment_issues.append(
                "Runtime manifest MCP URL drift detected for "
                f"`{server_name}` (expected `{expected_url}`, found `{manifest_url or 'missing'}`)."
            )

    for service_name, expected_url in sorted(expected_health_urls.items()):
        manifest_url = manifest_health_urls.get(service_name, "")
        if manifest_url != expected_url:
            alignment_issues.append(
                "Runtime manifest health URL drift detected for "
                f"`{service_name}` (expected `{expected_url}`, found `{manifest_url or 'missing'}`)."
            )

    docker_available = shutil.which("docker") is not None
    service_inventory: dict[str, dict[str, Any]] = {}
    if docker_available:
        try:
            service_inventory = collect_service_inventory(config.compose_project_name)
        except subprocess.CalledProcessError as exc:
            return {
                "status": "docker-error",
                "recommended_action": "inspect-docker",
                "issues": [
                    "Unable to inspect Docker runtime state for compose project "
                    f"`{config.compose_project_name}`: {exc}`"
                ],
                "config": config,
                "workspace_urls": workspace_urls,
                "manifest_server_urls": manifest_server_urls,
                "service_inventory": service_inventory,
                "expected_service_ports": expected_service_ports,
            }
    else:
        return {
            "status": "docker-unavailable",
            "recommended_action": "install-docker",
            "issues": ["Docker CLI is not available on PATH."],
            "config": config,
            "workspace_urls": workspace_urls,
            "manifest_server_urls": manifest_server_urls,
            "service_inventory": service_inventory,
            "expected_service_ports": expected_service_ports,
        }

    service_issues: list[str] = []
    port_issues: list[str] = []
    running_service_count = 0
    all_expected_services = [
        *factory_workspace.RUNTIME_SERVICE_CONTRACT.keys(),
        *WORKSPACE_SERVICE_PORT_KEYS.keys(),
    ]
    all_expected_service_names = sorted(set(all_expected_services))

    for service_name in all_expected_service_names:
        service_entry = service_inventory.get(service_name)
        if not service_entry:
            service_issues.append(
                "Expected runtime service is missing for compose project "
                f"`{config.compose_project_name}`: `{service_name}`."
            )
            continue

        status = str(service_entry.get("status", "")).strip().lower()
        if "up" in status:
            running_service_count += 1

        metadata = factory_workspace.RUNTIME_SERVICE_CONTRACT.get(service_name)
        requires_health = bool(metadata["require_healthy_status"] if metadata else True)
        if "up" not in status:
            service_issues.append(
                "Runtime service "
                f"`{service_name}` is not currently running "
                f"(docker status: `{service_entry.get('status', '')}`)."
            )
        elif requires_health and "healthy" not in status:
            service_issues.append(
                "Runtime service "
                f"`{service_name}` is running without a healthy status "
                f"(docker status: `{service_entry.get('status', '')}`)."
            )

        expected_port = expected_service_ports.get(service_name)
        published_ports = service_entry.get("published_ports", [])
        if expected_port is not None and expected_port not in published_ports:
            port_issues.append(
                "Runtime service "
                f"`{service_name}` is not published on expected host port "
                f"`{expected_port}` (found `{published_ports or 'none'}`)."
            )

    if alignment_issues or port_issues:
        status = "config-drift"
        recommended_action = "re-bootstrap"
        issues = [*alignment_issues, *port_issues]
    elif running_service_count == 0:
        status = "needs-ramp-up"
        recommended_action = "start"
        issues = [
            "Runtime preflight detected no running containers for compose project "
            f"`{config.compose_project_name}`. Infrastructure needs ramp-up via `factory_stack.py start`."
        ]
    elif service_issues:
        status = "degraded"
        recommended_action = "inspect"
        issues = service_issues
    else:
        status = "ready"
        recommended_action = "none"
        issues = []

    return {
        "status": status,
        "recommended_action": recommended_action,
        "issues": issues,
        "config": config,
        "workspace_urls": workspace_urls,
        "manifest_server_urls": manifest_server_urls,
        "manifest_health_urls": manifest_health_urls,
        "expected_service_ports": expected_service_ports,
        "service_inventory": service_inventory,
    }


def print_preflight_report(report: dict[str, Any]) -> None:
    config = report["config"]
    print(f"workspace_id={config.project_workspace_id}")
    print(f"instance_id={config.factory_instance_id}")
    print(f"target={config.target_dir}")
    print(f"compose_project={config.compose_project_name}")
    print(f"preflight_status={report['status']}")
    print(f"recommended_action={report['recommended_action']}")
    print(f"issue_count={len(report['issues'])}")

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
) -> int:
    report = build_preflight_report(
        repo_root,
        env_file=env_file,
        workspace_file=workspace_file,
    )
    print_preflight_report(report)
    return 0 if report["status"] == "ready" else 1


def infer_runtime_state_from_services(running_services: dict[str, str]) -> str:
    """Infer effective runtime state from observed Docker service statuses."""
    if not running_services:
        return "stopped"

    required_services = factory_workspace.RUNTIME_SERVICE_CONTRACT
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
    factory_workspace.update_runtime_state(config.factory_instance_id, "starting")
    if foreground:
        try:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, "running"
            )
            run_compose_command(
                repo_root,
                build_compose_command(repo_root, resolved_env_file, action),
            )
        except subprocess.CalledProcessError:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, "stopped"
            )
            raise
        except KeyboardInterrupt:
            print("\nShutting down stack...")
        finally:
            factory_workspace.update_runtime_state(
                config.factory_instance_id, "stopped"
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
        inferred_state = infer_runtime_state_from_services(running_services)
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

    run_compose_command(
        repo_root,
        build_compose_command(repo_root, resolved_env_file, action),
    )
    if not preserve_runtime_state:
        factory_workspace.update_runtime_state(config.factory_instance_id, "stopped")
    return resolved_env_file


def cleanup_workspace(
    repo_root: Path,
    *,
    env_file: Path | None = None,
) -> int:
    import shutil

    resolved_env_file = resolve_env_file(repo_root, env_file)
    config: factory_workspace.WorkspaceRuntimeConfig | None = None
    target_path = repo_root.parents[1]
    try:
        config = sync_workspace_runtime(
            repo_root, env_file=resolved_env_file, persist=False
        )
        target_path_str = str(config.target_dir.absolute())
        target_path = config.target_dir
        instance_id = config.factory_instance_id
        action = ["down", "-v", "--remove-orphans"]
        run_compose_command(
            repo_root,
            build_compose_command(repo_root, resolved_env_file, action),
        )
        print(f"🧹 Removed Docker stack and volumes for {instance_id}")
    except Exception as e:
        print(f"⚠️ Could not completely remove docker stack (it may not exist): {e}")
        target_path_str = str(repo_root.parents[1].absolute())

    registry = factory_workspace.load_registry()
    if "workspaces" in registry:
        # Also clean up any that map to this directory
        keys_to_delete = []
        for key, record in registry["workspaces"].items():
            if (
                isinstance(record, dict)
                and Path(record.get("target_workspace_path", "")).absolute()
                == Path(target_path_str).absolute()
            ):
                keys_to_delete.append(key)
        for key in keys_to_delete:
            del registry["workspaces"][key]
            if registry.get("active_workspace") == key:
                registry["active_workspace"] = ""
            print(f"🧹 Removed registry record {key}")
        factory_workspace.save_registry(registry)

    if resolved_env_file.exists():
        resolved_env_file.unlink()
        print(f"🧹 Deleted {resolved_env_file}")

    manifest_path = (
        target_path
        / factory_workspace.TMP_SUBPATH
        / factory_workspace.RUNTIME_MANIFEST_FILENAME
    )
    if manifest_path.exists():
        manifest_path.unlink()
        print(f"🧹 Deleted {manifest_path}")

    # Remove configured data directories for this instance.
    try:
        if config is not None:
            data_dir_str = str(config.env_values.get("FACTORY_DATA_DIR", "")).strip()
            if data_dir_str:
                data_dir = Path(data_dir_str).expanduser()
                instance_memory_dir = data_dir / "memory" / instance_id
                instance_bus_dir = data_dir / "bus" / instance_id
                for instance_dir in (instance_memory_dir, instance_bus_dir):
                    if instance_dir.exists() and instance_dir.is_dir():
                        shutil.rmtree(instance_dir, ignore_errors=True)
                        print(f"🧹 Erased data directory {instance_dir}")
    except Exception as e:
        print(f"⚠️ Could not fully erase configured data directories: {e}")

    return 0


def list_workspaces() -> int:
    res = factory_workspace.reconcile_registry()
    if res.get("stale_removed"):
        for stale_id in res["stale_removed"]:
            print(f"🧹 Removed stale registry record for: {stale_id}")
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


def status_workspace(repo_root: Path, *, env_file: Path | None = None) -> int:
    resolved_env_file = resolve_env_file(repo_root, env_file)
    config = sync_workspace_runtime(
        repo_root, env_file=resolved_env_file, persist=False
    )
    registry = factory_workspace.load_registry()
    record = registry.get("workspaces", {}).get(config.factory_instance_id, {})
    try:
        running_services = collect_running_services(config.compose_project_name)
    except subprocess.CalledProcessError:
        running_services = {}

    inferred_state = infer_runtime_state_from_services(running_services)
    persisted_state = str(record.get("runtime_state", "installed"))
    runtime_state = inferred_state if inferred_state != "stopped" else persisted_state
    if runtime_state != persisted_state:
        factory_workspace.update_runtime_state(
            config.factory_instance_id, runtime_state
        )

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
    print(f"workspace_id={config.project_workspace_id}")
    print(f"instance_id={config.factory_instance_id}")
    print(f"target={config.target_dir}")
    print(f"compose_project={config.compose_project_name}")
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
    preflight = build_preflight_report(repo_root, env_file=resolved_env_file)
    print(f"preflight_status={preflight['status']}")
    print(f"recommended_action={preflight['recommended_action']}")
    for name, url in sorted(config.mcp_server_urls.items()):
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
        description="Canonical Software Factory runtime start/stop helper."
    )
    parser.add_argument(
        "command",
        choices=[
            "start",
            "stop",
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
        help="Build images while starting the stack.",
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
        help="Also remove named volumes while stopping the stack.",
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
    elif args.command == "cleanup":
        return cleanup_workspace(
            repo_root,
            env_file=env_file,
        )
    elif args.command == "list":
        return list_workspaces()
    elif args.command == "status":
        return status_workspace(repo_root, env_file=env_file)
    elif args.command == "preflight":
        return preflight_workspace(
            repo_root,
            env_file=env_file,
            workspace_file=args.workspace_file,
        )
    elif args.command == "activate":
        return activate_workspace(repo_root, env_file=env_file)
    else:
        return deactivate_workspace(repo_root, env_file=env_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
