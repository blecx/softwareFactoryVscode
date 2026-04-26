from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from http.client import RemoteDisconnected
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import httpx
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


def _load_validate_throwaway_module():
    spec = importlib.util.spec_from_file_location(
        "validate_throwaway_install_under_test",
        VALIDATE_THROWAWAY_SCRIPT,
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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


def _parse_env_file(env_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key] = value
    return values


def _extract_output_value(output: str, key: str) -> str:
    prefix = f"{key}="
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"Expected `{key}` in command output:\n{output}")


def _mcp_tool_call(
    base_url: str,
    tool_name: str,
    arguments: dict[str, object],
    *,
    workspace_id: str,
) -> object:
    from factory_runtime.agents.mcp_client import (
        DEFAULT_MCP_PROTOCOL_VERSION,
        MCP_ACCEPT_HEADER,
        MCP_PROTOCOL_VERSION_HEADER,
        MCP_SESSION_ID_HEADER,
    )

    endpoint_url = f"{base_url.rstrip('/')}/mcp"
    headers = {
        "Content-Type": "application/json",
        MCP_PROTOCOL_VERSION_HEADER: DEFAULT_MCP_PROTOCOL_VERSION,
        "Accept": MCP_ACCEPT_HEADER,
        "X-Workspace-ID": workspace_id,
    }

    with httpx.Client(timeout=10.0) as client:
        init_response = client.post(
            endpoint_url,
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": DEFAULT_MCP_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "docker-multi-tenant-proof",
                        "version": "1.0",
                    },
                },
            },
        )
        init_response.raise_for_status()

        session_headers = dict(headers)
        session_id = init_response.headers.get(MCP_SESSION_ID_HEADER)
        if session_id:
            session_headers[MCP_SESSION_ID_HEADER] = session_id

        notify_response = client.post(
            endpoint_url,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            },
        )
        notify_response.raise_for_status()

        call_response = client.post(
            endpoint_url,
            headers=session_headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            },
        )
        call_response.raise_for_status()

    data = call_response.json()
    if "error" in data:
        error = data["error"]
        message = error.get("message") if isinstance(error, dict) else str(error)
        raise RuntimeError(str(message))

    result = data.get("result", {})
    if isinstance(result, dict):
        structured = result.get("structuredContent")
        if structured is not None:
            payload: object = structured
        else:
            payload = result
            content = result.get("content", [])
            if content:
                raw = content[0].get("text", "{}")
                try:
                    payload = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    payload = raw

        if result.get("isError"):
            raise RuntimeError(str(payload))

        return payload

    return result


def _seed_pending_run_via_mcp(
    bus_url: str,
    *,
    workspace_id: str,
    issue_number: int,
    repo: str,
    goal: str,
) -> str:
    run = _mcp_tool_call(
        bus_url,
        "bus_create_run",
        {"issue_number": issue_number, "repo": repo},
        workspace_id=workspace_id,
    )
    assert isinstance(run, dict)
    run_id = str(run["run_id"])
    _mcp_tool_call(
        bus_url,
        "bus_set_status",
        {"run_id": run_id, "status": "routing"},
        workspace_id=workspace_id,
    )
    _mcp_tool_call(
        bus_url,
        "bus_set_status",
        {"run_id": run_id, "status": "planning"},
        workspace_id=workspace_id,
    )
    _mcp_tool_call(
        bus_url,
        "bus_write_plan",
        {
            "run_id": run_id,
            "goal": goal,
            "files": ["src/example.py"],
            "acceptance_criteria": ["criterion"],
            "validation_cmds": ["pytest tests/test_multi_tenant.py"],
        },
        workspace_id=workspace_id,
    )
    _mcp_tool_call(
        bus_url,
        "bus_set_status",
        {"run_id": run_id, "status": "awaiting_approval"},
        workspace_id=workspace_id,
    )
    return run_id


def _docker_compose_project_images(compose_project_name: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            "{{.Image}}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})


def _docker_compose_project_container_ids(compose_project_name: str) -> list[str]:
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            "{{.ID}}",
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _verify_runtime_install(
    target_repo: Path,
    repo_root: Path,
    env: dict[str, str],
    *,
    attempts: int = 1,
    delay_seconds: float = 2.0,
) -> None:
    command = [
        str(repo_root / ".venv" / "bin" / "python"),
        str(repo_root / "scripts" / "verify_factory_install.py"),
        "--target",
        str(target_repo),
        "--runtime",
        "--check-vscode-mcp",
    ]

    last_result: subprocess.CompletedProcess[str] | None = None
    for attempt in range(max(1, attempts)):
        result = subprocess.run(
            command,
            cwd=target_repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            return
        last_result = result
        if attempt + 1 < attempts:
            time.sleep(delay_seconds)

    assert last_result is not None
    raise AssertionError(
        "Runtime verification did not reach a ready manager-backed state.\n"
        f"stdout:\n{last_result.stdout}\n\n"
        f"stderr:\n{last_result.stderr}"
    )


def _docker_image_exists(image_name: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", image_name],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _run_checked_process(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    step_name: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return result

    stdout = result.stdout if result.stdout else "<empty>\n"
    stderr = result.stderr if result.stderr else "<empty>\n"
    raise AssertionError(
        f"{step_name} failed with exit code {result.returncode}.\n"
        f"command: {shlex.join(command)}\n\n"
        f"stdout:\n{stdout}\n"
        f"stderr:\n{stderr}"
    )


def test_validate_throwaway_runtime_relocates_system_tmp_target() -> None:
    module = _load_validate_throwaway_module()

    source_repo = Path("/home/example/softwareFactoryVscode")
    requested_target = Path("/tmp/throwaway-target")

    effective_target, note = module.resolve_effective_target_repo(
        source_repo,
        requested_target,
        runtime_enabled=True,
    )

    assert (
        effective_target
        == (
            source_repo / ".tmp" / "throwaway-targets" / requested_target.name
        ).resolve()
    )
    assert note is not None
    assert "bind-mountable by Docker" in note


def test_validate_throwaway_static_run_defaults_to_repo_local_tmp_target() -> None:
    module = _load_validate_throwaway_module()

    source_repo = Path("/home/example/softwareFactoryVscode")
    requested_target = Path("/tmp/throwaway-target")

    effective_target, note = module.resolve_effective_target_repo(
        source_repo,
        requested_target,
        runtime_enabled=False,
    )

    assert (
        effective_target
        == (
            source_repo / ".tmp" / "throwaway-targets" / requested_target.name
        ).resolve()
    )
    assert note is not None
    assert "gitignored .tmp/ guardrail" in note


def test_validate_throwaway_preserves_repo_local_tmp_targets() -> None:
    module = _load_validate_throwaway_module()

    source_repo = Path("/home/example/softwareFactoryVscode")
    requested_target = source_repo / ".tmp" / "sandbox" / "throwaway-target"

    effective_target, note = module.resolve_effective_target_repo(
        source_repo,
        requested_target,
        runtime_enabled=True,
    )

    assert effective_target == requested_target.resolve()
    assert note is None


def test_validate_throwaway_allows_explicit_external_targets() -> None:
    module = _load_validate_throwaway_module()

    source_repo = Path("/home/example/softwareFactoryVscode")
    requested_target = Path("/home/example/other-workspace/throwaway-target")

    effective_target, note = module.resolve_effective_target_repo(
        source_repo,
        requested_target,
        runtime_enabled=False,
        allow_external_target=True,
    )

    assert effective_target == requested_target.resolve()
    assert note is None


def test_validate_throwaway_runtime_relocates_explicit_tmp_even_with_custom_tmpdir(
    monkeypatch,
) -> None:
    module = _load_validate_throwaway_module()
    monkeypatch.setattr(
        module.tempfile, "gettempdir", lambda: "/home/example/custom-tmp"
    )

    source_repo = Path("/home/example/softwareFactoryVscode")
    requested_target = Path("/tmp/throwaway-target")

    effective_target, note = module.resolve_effective_target_repo(
        source_repo,
        requested_target,
        runtime_enabled=True,
    )

    assert (
        effective_target
        == (
            source_repo / ".tmp" / "throwaway-targets" / requested_target.name
        ).resolve()
    )
    assert note is not None


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
                "factory_dir": str(
                    tmp_path / "seed" / ".copilot/softwareFactoryVscode"
                ),
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
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"

    try:
        subprocess.run(
            [
                sys.executable,
                str(VALIDATE_THROWAWAY_SCRIPT),
                "--target",
                str(target_repo),
                "--skip-runtime",
                "--skip-source-stack-handoff",
                "--allow-external-target",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        env_values = _parse_env_file(env_path)
        env_values["CONTEXT7_API_KEY"] = "test-context7-key"
        env_path.write_text(
            "\n".join(f"{key}={value}" for key, value in env_values.items()) + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "start",
                "--repo-root",
                str(target_repo / ".copilot/softwareFactoryVscode"),
                "--env-file",
                str(target_repo / ".copilot/softwareFactoryVscode/.factory.env"),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        runtime_manifest_path = (
            target_repo
            / ".copilot/softwareFactoryVscode/.tmp"
            / "runtime-manifest.json"
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
        env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
        if (
            env_path.exists()
            and (target_repo / ".copilot/softwareFactoryVscode").exists()
        ):
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


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_E2E", "0") != "1",
    reason="Set RUN_DOCKER_E2E=1 to run Docker-enabled throwaway runtime E2E tests.",
)
def test_throwaway_runtime_strict_tenant_mode_blocks_cross_tenant_approval_leaks(
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
                "factory_dir": str(
                    tmp_path / "seed" / ".copilot/softwareFactoryVscode"
                ),
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
                "--allow-external-target",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
        env_text = env_path.read_text(encoding="utf-8")
        if not env_text.endswith("\n"):
            env_text += "\n"
        env_path.write_text(
            env_text + "FACTORY_TENANCY_MODE=shared\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "start",
                "--repo-root",
                str(target_repo / ".copilot/softwareFactoryVscode"),
                "--env-file",
                str(env_path),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        env_values = _parse_env_file(env_path)
        approval_url = f"http://127.0.0.1:{env_values['APPROVAL_GATE_PORT']}"
        bus_url = f"http://127.0.0.1:{env_values['AGENT_BUS_PORT']}"
        memory_url = f"http://127.0.0.1:{env_values['MEMORY_MCP_PORT']}"

        assert _wait_until_reachable(f"{approval_url}/health")

        _mcp_tool_call(
            memory_url,
            "memory_store_lesson",
            {
                "issue_number": 1101,
                "outcome": "success",
                "summary": "tenant A lesson",
                "learnings": ["A stays isolated"],
                "repo": "org/tenant-a",
            },
            workspace_id="tenant-A",
        )
        _mcp_tool_call(
            memory_url,
            "memory_store_lesson",
            {
                "issue_number": 1102,
                "outcome": "success",
                "summary": "tenant B lesson",
                "learnings": ["B stays isolated"],
                "repo": "org/tenant-b",
            },
            workspace_id="tenant-B",
        )

        lessons_a = _mcp_tool_call(
            memory_url,
            "memory_get_recent",
            {"limit": 10},
            workspace_id="tenant-A",
        )
        lessons_b = _mcp_tool_call(
            memory_url,
            "memory_get_recent",
            {"limit": 10},
            workspace_id="tenant-B",
        )

        assert isinstance(lessons_a, dict)
        assert isinstance(lessons_b, dict)
        assert [lesson["summary"] for lesson in lessons_a["lessons"]] == [
            "tenant A lesson"
        ]
        assert [lesson["summary"] for lesson in lessons_b["lessons"]] == [
            "tenant B lesson"
        ]

        run_a = _seed_pending_run_via_mcp(
            bus_url,
            workspace_id="tenant-A",
            issue_number=1201,
            repo="org/tenant-a",
            goal="Tenant A docker-backed plan",
        )
        run_b = _seed_pending_run_via_mcp(
            bus_url,
            workspace_id="tenant-B",
            issue_number=1202,
            repo="org/tenant-b",
            goal="Tenant B docker-backed plan",
        )

        with pytest.raises(RuntimeError, match="Run not found for project"):
            _mcp_tool_call(
                bus_url,
                "bus_read_context_packet",
                {"run_id": run_a},
                workspace_id="tenant-B",
            )

        with httpx.Client(timeout=10.0) as client:
            pending_a = client.get(
                f"{approval_url}/pending",
                headers={"X-Workspace-ID": "tenant-A"},
            )
            pending_b = client.get(
                f"{approval_url}/pending",
                headers={"X-Workspace-ID": "tenant-B"},
            )

            assert pending_a.status_code == 200
            assert pending_b.status_code == 200
            assert [run["run_id"] for run in pending_a.json()] == [run_a]
            assert [run["run_id"] for run in pending_b.json()] == [run_b]

            wrong_plan = client.get(
                f"{approval_url}/plan/{run_a}",
                headers={"X-Workspace-ID": "tenant-B"},
            )
            wrong_approve = client.post(
                f"{approval_url}/approve/{run_a}",
                headers={"X-Workspace-ID": "tenant-B"},
                json={"approved": True, "feedback": "wrong tenant"},
            )
            wrong_reject = client.post(
                f"{approval_url}/approve/{run_b}",
                headers={"X-Workspace-ID": "tenant-A"},
                json={"approved": False, "feedback": "wrong tenant"},
            )

            assert wrong_plan.status_code == 404
            assert wrong_approve.status_code == 400
            assert wrong_reject.status_code == 400
            assert "Run not found for project" in wrong_plan.json()["detail"]
            assert "Run not found for project" in wrong_approve.json()["detail"]
            assert "Run not found for project" in wrong_reject.json()["detail"]

            approve_a = client.post(
                f"{approval_url}/approve/{run_a}",
                headers={"X-Workspace-ID": "tenant-A"},
                json={"approved": True, "feedback": "looks good"},
            )
            reject_b = client.post(
                f"{approval_url}/approve/{run_b}",
                headers={"X-Workspace-ID": "tenant-B"},
                json={"approved": False, "feedback": "needs work"},
            )

            assert approve_a.status_code == 200
            assert reject_b.status_code == 200

        packet_a = _mcp_tool_call(
            bus_url,
            "bus_read_context_packet",
            {"run_id": run_a},
            workspace_id="tenant-A",
        )
        packet_b = _mcp_tool_call(
            bus_url,
            "bus_read_context_packet",
            {"run_id": run_b},
            workspace_id="tenant-B",
        )

        assert isinstance(packet_a, dict)
        assert isinstance(packet_b, dict)
        assert packet_a["run"]["status"] == "approved"
        assert packet_b["run"]["status"] == "failed"
    finally:
        env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
        if (
            env_path.exists()
            and (target_repo / ".copilot/softwareFactoryVscode").exists()
        ):
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


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_E2E", "0") != "1",
    reason="Set RUN_DOCKER_E2E=1 to run Docker-enabled throwaway runtime E2E tests.",
)
def test_throwaway_runtime_activate_switch_back_keeps_one_active_workspace(
    tmp_path: Path,
) -> None:
    if not _docker_ready():
        pytest.skip("Docker CLI is not available on PATH.")

    target_repo_a = tmp_path / "throwaway-target-a"
    target_repo_b = tmp_path / "throwaway-target-b"
    registry_path = tmp_path / "registry.json"

    env = os.environ.copy()
    env["SOFTWARE_FACTORY_REGISTRY_PATH"] = str(registry_path)

    repo_root_a = target_repo_a / ".copilot/softwareFactoryVscode"
    repo_root_b = target_repo_b / ".copilot/softwareFactoryVscode"
    env_path_a = repo_root_a / ".factory.env"
    env_path_b = repo_root_b / ".factory.env"

    try:
        for target_repo in (target_repo_a, target_repo_b):
            subprocess.run(
                [
                    sys.executable,
                    str(VALIDATE_THROWAWAY_SCRIPT),
                    "--target",
                    str(target_repo),
                    "--skip-runtime",
                    "--skip-source-stack-handoff",
                    "--allow-external-target",
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
                "activate",
                "--repo-root",
                str(repo_root_a),
                "--env-file",
                str(env_path_a),
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
                str(repo_root_a),
                "--env-file",
                str(env_path_a),
                "--build",
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
                "activate",
                "--repo-root",
                str(repo_root_b),
                "--env-file",
                str(env_path_b),
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
                str(repo_root_b),
                "--env-file",
                str(env_path_b),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        manifest_a = json.loads(
            (repo_root_a / ".tmp" / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        manifest_b = json.loads(
            (repo_root_b / ".tmp" / "runtime-manifest.json").read_text(encoding="utf-8")
        )
        context7_url_a = manifest_a["mcp_servers"]["context7"]["url"]
        context7_url_b = manifest_b["mcp_servers"]["context7"]["url"]

        assert _wait_until_reachable(context7_url_a)
        assert _wait_until_reachable(context7_url_b)

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "activate",
                "--repo-root",
                str(repo_root_a),
                "--env-file",
                str(env_path_a),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        status_a = subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "status",
                "--repo-root",
                str(repo_root_a),
                "--env-file",
                str(env_path_a),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        status_b = subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "status",
                "--repo-root",
                str(repo_root_b),
                "--env-file",
                str(env_path_b),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )

        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        workspace_a = json.loads(
            (target_repo_a / "software-factory.code-workspace").read_text(
                encoding="utf-8"
            )
        )
        workspace_b = json.loads(
            (target_repo_b / "software-factory.code-workspace").read_text(
                encoding="utf-8"
            )
        )

        assert registry["active_workspace"] == manifest_a["factory_instance_id"]
        assert "active=true" in status_a.stdout
        assert "active=false" in status_b.stdout
        assert f"mcp.context7={context7_url_a}" in status_a.stdout
        assert f"mcp.context7={context7_url_b}" in status_b.stdout
        assert (
            workspace_a["settings"]["mcp"]["servers"]["context7"]["url"]
            == context7_url_a
        )
        assert (
            workspace_b["settings"]["mcp"]["servers"]["context7"]["url"]
            == context7_url_b
        )
        assert context7_url_a != context7_url_b
    finally:
        for repo_root, env_path in (
            (repo_root_b, env_path_b),
            (repo_root_a, env_path_a),
        ):
            if env_path.exists() and repo_root.exists():
                subprocess.run(
                    [
                        sys.executable,
                        str(FACTORY_STACK_SCRIPT),
                        "stop",
                        "--repo-root",
                        str(repo_root),
                        "--env-file",
                        str(env_path),
                        "--remove-volumes",
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                    text=True,
                    check=False,
                )


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_E2E", "0") != "1",
    reason="Set RUN_DOCKER_E2E=1 to run Docker-enabled throwaway runtime E2E tests.",
)
def test_throwaway_runtime_stop_cleanup_retains_images_and_supports_restart(
    tmp_path: Path,
) -> None:
    if not _docker_ready():
        pytest.skip("Docker CLI is not available on PATH.")

    target_repo = tmp_path / "throwaway-target"
    registry_path = tmp_path / "registry.json"

    env = os.environ.copy()
    env["SOFTWARE_FACTORY_REGISTRY_PATH"] = str(registry_path)

    repo_root = target_repo / ".copilot/softwareFactoryVscode"
    env_path = repo_root / ".factory.env"
    manifest_path = repo_root / ".tmp" / "runtime-manifest.json"

    try:
        subprocess.run(
            [
                sys.executable,
                str(VALIDATE_THROWAWAY_SCRIPT),
                "--target",
                str(target_repo),
                "--skip-runtime",
                "--skip-source-stack-handoff",
                "--allow-external-target",
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
                str(repo_root),
                "--env-file",
                str(env_path),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        compose_project_name = str(manifest["compose_project_name"])
        context7_url = str(manifest["mcp_servers"]["context7"]["url"])

        assert _wait_until_reachable(context7_url)

        images = _docker_compose_project_images(compose_project_name)
        assert images
        retained_image = next(
            (image for image in images if "factory" in image.lower()),
            images[0],
        )

        stop_result = _run_checked_process(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "stop",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
                "--remove-volumes",
            ],
            cwd=REPO_ROOT,
            env=env,
            step_name="throwaway runtime stop validation",
        )

        assert "Removed containers and named volumes" in stop_result.stdout
        assert "retained Docker images" in stop_result.stdout
        assert env_path.exists()
        assert manifest_path.exists()
        assert _docker_compose_project_container_ids(compose_project_name) == []
        assert _docker_image_exists(retained_image)

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "start",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        assert _wait_until_reachable(context7_url)

        cleanup_result = _run_checked_process(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "cleanup",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            step_name="throwaway runtime cleanup validation",
        )

        assert (
            "`cleanup` removed workspace containers and named volumes when present"
            in cleanup_result.stdout
        )
        assert "Docker images were retained" in cleanup_result.stdout
        assert not env_path.exists()
        assert not manifest_path.exists()
        assert _docker_compose_project_container_ids(compose_project_name) == []
        assert _docker_image_exists(retained_image)
    finally:
        if env_path.exists() and repo_root.exists():
            subprocess.run(
                [
                    sys.executable,
                    str(FACTORY_STACK_SCRIPT),
                    "stop",
                    "--repo-root",
                    str(repo_root),
                    "--env-file",
                    str(env_path),
                    "--remove-volumes",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                check=False,
            )


@pytest.mark.docker
@pytest.mark.skipif(
    os.getenv("RUN_DOCKER_E2E", "0") != "1",
    reason="Set RUN_DOCKER_E2E=1 to run Docker-enabled throwaway runtime E2E tests.",
)
def test_throwaway_runtime_backup_restore_roundtrip_recovers_state_and_runtime_contract(
    tmp_path: Path,
) -> None:
    if not _docker_ready():
        pytest.skip("Docker CLI is not available on PATH.")

    target_repo = tmp_path / "throwaway-target"
    registry_path = tmp_path / "registry.json"

    env = os.environ.copy()
    env["SOFTWARE_FACTORY_REGISTRY_PATH"] = str(registry_path)

    repo_root = target_repo / ".copilot/softwareFactoryVscode"
    env_path = repo_root / ".factory.env"
    manifest_path = repo_root / ".tmp" / "runtime-manifest.json"

    try:
        subprocess.run(
            [
                sys.executable,
                str(VALIDATE_THROWAWAY_SCRIPT),
                "--target",
                str(target_repo),
                "--skip-runtime",
                "--skip-source-stack-handoff",
                "--allow-external-target",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        seeded_env_values = _parse_env_file(env_path)
        seeded_env_values["FACTORY_RUNTIME_MODE"] = "production"
        seeded_env_values["CONTEXT7_API_KEY"] = "test-context7-key"
        seeded_env_values["GITHUB_TOKEN"] = "test-github-token"
        seeded_env_values["GITHUB_OPS_ALLOWED_REPOS"] = "blecx/softwareFactoryVscode"
        env_path.write_text(
            "\n".join(f"{key}={value}" for key, value in seeded_env_values.items())
            + "\n",
            encoding="utf-8",
        )

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "start",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
                "--build",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        compose_project_name = str(manifest["compose_project_name"])

        env_values = _parse_env_file(env_path)
        workspace_id = env_values["PROJECT_WORKSPACE_ID"]
        approval_url = f"http://127.0.0.1:{env_values['APPROVAL_GATE_PORT']}"
        bus_url = f"http://127.0.0.1:{env_values['AGENT_BUS_PORT']}"
        memory_url = f"http://127.0.0.1:{env_values['MEMORY_MCP_PORT']}"

        assert _wait_until_reachable(f"{approval_url}/health")

        _mcp_tool_call(
            memory_url,
            "memory_store_lesson",
            {
                "issue_number": 108,
                "outcome": "success",
                "summary": "restore roundtrip lesson",
                "learnings": ["bundled state survives cleanup"],
                "repo": "blecx/softwareFactoryVscode",
            },
            workspace_id=workspace_id,
        )
        run_id = _seed_pending_run_via_mcp(
            bus_url,
            workspace_id=workspace_id,
            issue_number=108,
            repo="blecx/softwareFactoryVscode",
            goal="Restore roundtrip proof",
        )
        memory_db = (
            repo_root
            / "data"
            / "memory"
            / env_values["FACTORY_INSTANCE_ID"]
            / "memory.db"
        )
        agent_bus_db = (
            repo_root
            / "data"
            / "bus"
            / env_values["FACTORY_INSTANCE_ID"]
            / "agent_bus.db"
        )

        assert memory_db.exists()
        assert agent_bus_db.exists()
        assert os.access(memory_db.parent, os.W_OK), (
            "The throwaway runtime memory bind mount must stay writable by the "
            "host user so cleanup and restore can rewrite bundled state."
        )
        assert os.access(agent_bus_db.parent, os.W_OK), (
            "The throwaway runtime agent-bus bind mount must stay writable by the "
            "host user so cleanup and restore can rewrite bundled state."
        )

        pending_before = httpx.get(
            f"{approval_url}/pending",
            headers={"X-Workspace-ID": workspace_id},
            timeout=10.0,
        )
        pending_before.raise_for_status()
        assert [run["run_id"] for run in pending_before.json()] == [run_id]

        _verify_runtime_install(
            target_repo,
            repo_root,
            env,
            attempts=15,
            delay_seconds=2.0,
        )

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "suspend",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
                "--completed-tool-call-boundary",
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        backup_result = _run_checked_process(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "backup",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            step_name="throwaway runtime backup validation",
        )
        bundle_path = _extract_output_value(backup_result.stdout, "bundle_path")

        cleanup_result = _run_checked_process(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "cleanup",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            step_name="throwaway runtime cleanup-before-restore validation",
        )

        assert (
            "`cleanup` removed workspace containers and named volumes when present"
            in cleanup_result.stdout
        )
        assert not env_path.exists()
        assert not manifest_path.exists()
        assert _docker_compose_project_container_ids(compose_project_name) == []

        restore_result = _run_checked_process(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "restore",
                "--repo-root",
                str(repo_root),
                "--bundle-path",
                bundle_path,
            ],
            cwd=REPO_ROOT,
            env=env,
            step_name="throwaway runtime restore roundtrip validation",
        )

        assert "runtime_state=suspended" in restore_result.stdout
        assert "recommended_action=resume" in restore_result.stdout
        assert "recovery_classification=resume-safe" in restore_result.stdout
        assert "completed_tool_call_boundary=true" in restore_result.stdout
        assert env_path.exists()
        assert manifest_path.exists()

        subprocess.run(
            [
                sys.executable,
                str(FACTORY_STACK_SCRIPT),
                "resume",
                "--repo-root",
                str(repo_root),
                "--env-file",
                str(env_path),
            ],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            check=True,
        )

        assert _wait_until_reachable(f"{approval_url}/health")

        _verify_runtime_install(
            target_repo,
            repo_root,
            env,
            attempts=10,
            delay_seconds=2.0,
        )

        lessons = _mcp_tool_call(
            memory_url,
            "memory_get_recent",
            {"limit": 10},
            workspace_id=workspace_id,
        )
        assert isinstance(lessons, dict)
        assert [lesson["summary"] for lesson in lessons["lessons"]] == [
            "restore roundtrip lesson"
        ]

        packet = _mcp_tool_call(
            bus_url,
            "bus_read_context_packet",
            {"run_id": run_id},
            workspace_id=workspace_id,
        )
        assert isinstance(packet, dict)
        assert packet["run"]["status"] == "awaiting_approval"

        pending_after = httpx.get(
            f"{approval_url}/pending",
            headers={"X-Workspace-ID": workspace_id},
            timeout=10.0,
        )
        pending_after.raise_for_status()
        assert [run["run_id"] for run in pending_after.json()] == [run_id]
    finally:
        if env_path.exists() and repo_root.exists():
            subprocess.run(
                [
                    sys.executable,
                    str(FACTORY_STACK_SCRIPT),
                    "stop",
                    "--repo-root",
                    str(repo_root),
                    "--env-file",
                    str(env_path),
                    "--remove-volumes",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                check=False,
            )
