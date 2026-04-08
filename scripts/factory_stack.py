#!/usr/bin/env python3
"""Canonical start/stop helper for the Software Factory runtime stack."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import factory_workspace

DEFAULT_WAIT_TIMEOUT = 300
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


def resolve_env_file(repo_root: Path, env_file: Path | None = None) -> Path:
    if env_file is not None:
        return env_file.expanduser().resolve()

    candidates = [repo_root / ".factory.env", repo_root.parent / ".factory.env"]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    return candidates[0].resolve()


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
    return repo_root.parent.resolve()


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


def ensure_ports_ready(config: factory_workspace.WorkspaceRuntimeConfig) -> None:
    try:
        running_services = collect_running_services(config.compose_project_name)
    except subprocess.CalledProcessError:
        running_services = {}
    if running_services:
        return
    if not factory_workspace.ports_available(config.ports):
        used_ports = [
            f"{key}={value}"
            for key, value in sorted(config.ports.items())
            if not factory_workspace.can_bind_port(value)
        ]
        raise RuntimeError(
            "Workspace runtime ports are not available: " + ", ".join(used_ports)
        )


def ensure_data_dirs_ready(config: factory_workspace.WorkspaceRuntimeConfig) -> None:
    data_dir_str = config.env_values.get("FACTORY_DATA_DIR")
    if data_dir_str:
        base_dir = Path(data_dir_str).expanduser()
        (base_dir / "memory" / config.factory_instance_id).mkdir(
            parents=True, exist_ok=True
        )
        (base_dir / "bus" / config.factory_instance_id).mkdir(
            parents=True, exist_ok=True
        )


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
    target_path = repo_root.parent
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
        target_path_str = str(repo_root.parent.absolute())

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
        target_path / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    )
    if manifest_path.exists():
        manifest_path.unlink()
        print(f"🧹 Deleted {manifest_path}")

    # Remove configured data directories for this instance.
    try:
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
    print(f"workspace_id={config.project_workspace_id}")
    print(f"instance_id={config.factory_instance_id}")
    print(f"target={config.target_dir}")
    print(f"compose_project={config.compose_project_name}")
    print(f"runtime_state={runtime_state}")
    print(f"active={str(active).lower()}")
    print(f"port_index={config.port_index}")
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
    factory_workspace.upsert_workspace_record(
        factory_workspace.build_runtime_manifest(config),
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
        help="Optional explicit .factory.env path. Defaults to repo-root/.factory.env or repo-root/../.factory.env.",
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
    elif args.command == "activate":
        return activate_workspace(repo_root, env_file=env_file)
    else:
        return deactivate_workspace(repo_root, env_file=env_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
