from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATE_THROWAWAY_SCRIPT = REPO_ROOT / "scripts" / "validate_throwaway_install.py"
FACTORY_STACK_SCRIPT = REPO_ROOT / "scripts" / "factory_stack.py"
REQUIRED_BASELINE_SERVERS = {
    "context7",
    "filesystem",
    "git",
    "search",
}


def _docker_ready() -> bool:
    return shutil.which("docker") is not None


def _url_is_reachable(url: str, timeout: float = 4.0) -> bool:
    try:
        with urlopen(url, timeout=timeout):
            return True
    except RemoteDisconnected:
        return True
    except HTTPError:
        # MCP endpoints often return 4xx on plain GET but still prove server reachability.
        return True
    except URLError:
        return False


def _wait_until_reachable(url: str, max_wait_seconds: int = 30) -> bool:
    deadline = time.time() + max_wait_seconds
    while time.time() < deadline:
        if _url_is_reachable(url):
            return True
        time.sleep(1.0)
    return _url_is_reachable(url)


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_E2E", "0") != "1",
    reason="Set RUN_DOCKER_E2E=1 to run Docker-enabled throwaway runtime E2E tests.",
)
def test_throwaway_runtime_uses_non_default_port_block_and_workspace_urls(
    tmp_path: Path,
) -> None:
    if not _docker_ready():
        pytest.skip("Docker CLI is not available on PATH.")

    target_repo = tmp_path / "throwaway-target"
    registry_path = tmp_path / "registry.json"

    seeded_registry = {
        "version": 1,
        "active_workspace": "",
        "workspaces": {
            "factory-seed": {
                "factory_instance_id": "factory-seed",
                "project_workspace_id": "seed",
                "target_workspace_path": str(tmp_path / "seed"),
                "factory_dir": str(tmp_path / "seed" / ".copilot/softwareFactoryVscode"),
                "workspace_file_path": str(
                    tmp_path / "seed" / "software-factory.code-workspace"
                ),
                "compose_project_name": "factory_seed",
                "port_index": 0,
                "ports": {
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
                },
                "factory_version": "seed",
                "runtime_state": "running",
                "installed_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        },
        "updated_at": "2026-01-01T00:00:00Z",
    }
    registry_path.write_text(
        json.dumps(seeded_registry, indent=2) + "\n", encoding="utf-8"
    )

    env = os.environ.copy()
    env["SOFTWARE_FACTORY_REGISTRY_PATH"] = str(registry_path)

    try:
        subprocess.run(
            [
                sys.executable,
                str(VALIDATE_THROWAWAY_SCRIPT),
                "--target",
                str(target_repo),
                "--skip-runtime",
                "--skip-source-stack-handoff",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "start",
                "--repo-root",
                str(target_repo / ".copilot/softwareFactoryVscode"),
                "--env-file",
                str(target_repo / ".factory.env"),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        runtime_manifest_path = (
            target_repo / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
        )
        runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
        assert runtime_manifest["port_index"] != 0

        workspace_path = target_repo / "software-factory.code-workspace"
        workspace_data = json.loads(workspace_path.read_text(encoding="utf-8"))
        mcp_servers = workspace_data["settings"]["mcp"]["servers"]

        reachable = {}
        for name, cfg in mcp_servers.items():
            url = cfg.get("url")
            if isinstance(url, str) and url.startswith("http://127.0.0.1"):
                reachable[name] = _wait_until_reachable(url)

        assert (
            reachable
        ), "No localhost MCP URLs were found in generated workspace settings."
        missing_baseline = [
            name
            for name in sorted(REQUIRED_BASELINE_SERVERS)
            if name not in reachable or not reachable[name]
        ]
        assert (
            not missing_baseline
        ), "Required baseline MCP URLs were not reachable: " + ", ".join(
            missing_baseline
        )
    finally:
        env_path = target_repo / ".factory.env"
        if env_path.exists() and (target_repo / ".copilot/softwareFactoryVscode").exists():
            subprocess.run(
                [
                    sys.executable,
                    str(FACTORY_STACK_SCRIPT),
                    "stop",
                    "--repo-root",
                    str(target_repo / ".copilot/softwareFactoryVscode"),
                    "--env-file",
                    str(env_path),
                    "--remove-volumes",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                check=False,
            )
