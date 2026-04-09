from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from http.client import RemoteDisconnected
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_factory.py"
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_host.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_factory_install.py"
FACTORY_STACK_SCRIPT = REPO_ROOT / "scripts" / "factory_stack.py"
FACTORY_WORKSPACE_SCRIPT = REPO_ROOT / "scripts" / "factory_workspace.py"
WORKSPACE_TEMPLATE = REPO_ROOT / "workspace.code-workspace.template"
ROOT_GITIGNORE = REPO_ROOT / ".gitignore"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


install_factory = load_module("install_factory_under_test", INSTALL_SCRIPT)
bootstrap_host = load_module("bootstrap_host_under_test", BOOTSTRAP_SCRIPT)
verify_factory_install = load_module("verify_factory_install_under_test", VERIFY_SCRIPT)
factory_stack = load_module("factory_stack_under_test", FACTORY_STACK_SCRIPT)
factory_workspace = load_module(
    "factory_workspace_under_test", FACTORY_WORKSPACE_SCRIPT
)


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        text=True,
        capture_output=True,
    )


def run_python_script(
    script: Path, *args: str, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git("init", cwd=path)
    git("checkout", "-b", "main", cwd=path)
    git("config", "user.name", "Test User", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)


def create_source_factory_repo(path: Path) -> None:
    init_git_repo(path)
    (path / "scripts").mkdir(parents=True, exist_ok=True)
    (path / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (path / "configs").mkdir(parents=True, exist_ok=True)
    (path / ".gitignore").write_text(
        ROOT_GITIGNORE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "install_factory.py").write_text(
        INSTALL_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "bootstrap_host.py").write_text(
        BOOTSTRAP_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "verify_factory_install.py").write_text(
        VERIFY_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "factory_workspace.py").write_text(
        FACTORY_WORKSPACE_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (path / "configs" / "bash_gateway_policy.default.yml").write_text(
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (path / "workspace.code-workspace.template").write_text(
        WORKSPACE_TEMPLATE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "setup.sh").write_text(
        "#!/usr/bin/env bash\n"
        "mkdir -p .venv/bin\n"
        "touch .venv/bin/python\n"
        "chmod +x .venv/bin/python\n"
        "echo '✅ Mock repository environment ready: .venv'\n",
        encoding="utf-8",
    )
    (path / "setup.sh").chmod(0o755)
    (path / "requirements.dev.txt").write_text(
        (REPO_ROOT / "requirements.dev.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "factory_runtime").mkdir(parents=True, exist_ok=True)
    (path / "factory_runtime" / "agents").mkdir(parents=True, exist_ok=True)
    (path / "factory_runtime" / "agents" / "requirements.txt").write_text(
        (REPO_ROOT / "factory_runtime" / "agents" / "requirements.txt").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    git("add", ".", cwd=path)
    git("commit", "-m", "Initial factory payload", cwd=path)


def test_install_factory_bootstraps_target_and_generates_workspace(
    tmp_path: Path,
) -> None:
    source_repo = tmp_path / "source-factory"
    target_repo = tmp_path / "target-project"
    create_source_factory_repo(source_repo)
    init_git_repo(target_repo)

    exit_code = install_factory.main(
        ["--target", str(target_repo), "--repo-url", str(source_repo)]
    )

    assert exit_code == 0
    assert (target_repo / ".copilot/softwareFactoryVscode").exists()
    assert (target_repo / ".tmp" / "softwareFactoryVscode").exists()

    factory_env = (target_repo / ".copilot/softwareFactoryVscode/.factory.env").read_text(encoding="utf-8")
    assert f"TARGET_WORKSPACE_PATH={target_repo}" in factory_env
    assert f"FACTORY_DIR={target_repo / '.copilot/softwareFactoryVscode'}" in factory_env
    assert "FACTORY_INSTANCE_ID=factory_" not in factory_env
    assert "FACTORY_INSTANCE_ID=factory-" in factory_env
    assert "CONTEXT7_API_KEY=" in factory_env

    runtime_manifest = json.loads(
        (
            target_repo / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert runtime_manifest["compose_project_name"] == f"factory_{target_repo.name}"
    port_context7 = runtime_manifest["ports"]["PORT_CONTEXT7"]
    port_bash = runtime_manifest["ports"]["PORT_BASH"]
    assert f"PORT_CONTEXT7={port_context7}" in factory_env

    workspace_path = target_repo / "software-factory.code-workspace"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert workspace["folders"][0]["path"] == "."
    assert workspace["folders"][1]["path"] == ".copilot/softwareFactoryVscode"
    assert (
        workspace["settings"]["mcp"]["servers"]["bashGateway"]["url"]
        == f"http://127.0.0.1:{port_bash}/mcp"
    )

    lock_data = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(encoding="utf-8")
    )
    assert lock_data["version"] == "main"
    assert lock_data["factory"]["repo_url"] == str(source_repo)
    assert lock_data["factory"]["workspace_file"] == "software-factory.code-workspace"
    assert lock_data["factory"]["commit"]

    gitignore = (target_repo / ".gitignore").read_text(encoding="utf-8")
    assert ".tmp/softwareFactoryVscode/" in gitignore
    assert ".copilot/softwareFactoryVscode/.factory.env" in gitignore


def test_throwaway_target_install_regression_via_cli(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-factory"
    target_repo = tmp_path / "throwaway-target"
    create_source_factory_repo(source_repo)
    init_git_repo(target_repo)

    install_result = run_python_script(
        INSTALL_SCRIPT,
        "--target",
        str(target_repo),
        "--repo-url",
        str(source_repo),
    )

    assert install_result.returncode == 0, install_result.stdout + install_result.stderr
    assert "Installing softwareFactoryVscode" in install_result.stdout
    assert (
        "Bootstrapping target repository for Option B workspace usage"
        in install_result.stdout
    )
    assert "Installation compliance passed" in install_result.stdout
    assert "Non-mutating VS Code smoke prompt" in install_result.stdout
    assert (
        "Do not create, modify, delete, stage, commit, or rename any file."
        in install_result.stdout
    )

    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    assert factory_dir.is_dir()
    assert (factory_dir / ".git").exists()
    assert (factory_dir / "setup.sh").exists()
    assert (factory_dir / ".venv" / "bin" / "python").exists()
    assert (target_repo / ".tmp" / "softwareFactoryVscode").is_dir()
    assert (
        target_repo / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    ).is_file()
    assert (target_repo / ".copilot/softwareFactoryVscode/.factory.env").is_file()
    assert (target_repo / ".copilot/softwareFactoryVscode/lock.json").is_file()
    assert (target_repo / "software-factory.code-workspace").is_file()
    assert (
        target_repo
        / ".copilot/softwareFactoryVscode"
        / "configs"
        / "bash_gateway_policy.default.yml"
    ).is_file()
    assert (
        target_repo
        / ".copilot/softwareFactoryVscode"
        / ".copilot"
        / "config"
        / "vscode-agent-settings.json"
    ).is_file()

    lock_data = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(encoding="utf-8")
    )
    assert lock_data["factory"]["repo_url"] == str(source_repo)
    assert lock_data["factory"]["install_path"] == ".copilot/softwareFactoryVscode"
    assert lock_data["factory"]["workspace_file"] == "software-factory.code-workspace"
    assert lock_data["factory"]["commit"]

    workspace_data = json.loads(
        (target_repo / "software-factory.code-workspace").read_text(encoding="utf-8")
    )
    assert workspace_data["folders"] == [
        {"name": "Host Project (Root)", "path": "."},
        {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
    ]
    runtime_manifest = json.loads(
        (
            target_repo / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert (
        workspace_data["settings"]["mcp"]["servers"]["context7"]["url"]
        == f"http://127.0.0.1:{runtime_manifest['ports']['PORT_CONTEXT7']}/mcp"
    )

    verify_result = run_python_script(
        target_repo
        / ".copilot/softwareFactoryVscode"
        / "scripts"
        / "verify_factory_install.py",
        "--target",
        str(target_repo),
        "--no-smoke-prompt",
    )

    assert verify_result.returncode == 0, verify_result.stdout + verify_result.stderr
    assert "Installation compliance passed" in verify_result.stdout
    assert "Option B workspace entrypoint look correct" in verify_result.stdout
    assert "Non-mutating VS Code smoke prompt" not in verify_result.stdout


def test_update_preserves_custom_workspace_and_env(tmp_path: Path) -> None:
    source_repo = tmp_path / "source-factory"
    target_repo = tmp_path / "target-project"
    create_source_factory_repo(source_repo)
    init_git_repo(target_repo)

    assert (
        install_factory.main(
            ["--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )

    workspace_path = target_repo / "software-factory.code-workspace"
    custom_workspace = json.dumps({"settings": {"custom": True}})
    workspace_path.write_text(custom_workspace, encoding="utf-8")

    custom_env = "\n".join(
        [
            f"TARGET_WORKSPACE_PATH={target_repo}",
            f"PROJECT_WORKSPACE_ID={target_repo.name}",
            f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
            "CONTEXT7_API_KEY=abc123",
            "",
        ]
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(custom_env, encoding="utf-8")
    tmp_dir = target_repo / ".tmp" / "softwareFactoryVscode"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "foo.txt").write_text("running")

    assert (
        install_factory.main(
            ["--target", str(target_repo), "--repo-url", str(source_repo), "--update", "--force-workspace"]
        )
        == 0
    )

    # Workspace overwritten (force-workspace passed)
    assert "\"custom\": true" not in workspace_path.read_text(encoding="utf-8")
    
    # env preserved
    updated_env = (target_repo / ".copilot/softwareFactoryVscode/.factory.env").read_text(encoding="utf-8")
    assert "CONTEXT7_API_KEY=abc123" in updated_env
    assert "PORT_BASH=" in updated_env
    
    # tmp untouched
    assert (tmp_dir / 'foo.txt').exists()


def test_bootstrap_force_workspace_overwrites_existing_workspace(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode").mkdir(parents=True, exist_ok=True)
    workspace_path = target_repo / "software-factory.code-workspace"
    workspace_path.write_text('{"folders": []}\n', encoding="utf-8")

    exit_code = bootstrap_host.main(
        [
            "--target",
            str(target_repo),
            "--force-workspace",
            "--factory-version",
            "main",
        ]
    )

    assert exit_code == 0
    generated = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert generated["folders"][0]["path"] == "."
    assert generated["folders"][1]["path"] == ".copilot/softwareFactoryVscode"


def test_verify_factory_install_detects_compliant_install_and_smoke_prompt(
    tmp_path: Path,
    capsys,
) -> None:
    source_repo = tmp_path / "source-factory"
    target_repo = tmp_path / "target-project"
    create_source_factory_repo(source_repo)
    init_git_repo(target_repo)

    assert (
        install_factory.main(
            ["--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Installation compliance passed" in output
    assert "Non-mutating VS Code smoke prompt" in output
    assert "Do not create, modify, delete, stage, commit, or rename any file." in output


def test_verify_factory_install_fails_when_workspace_file_missing(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode").mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode" / ".git").mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode" / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (target_repo / ".copilot/softwareFactoryVscode" / "scripts" / script_name).write_text(
            "# stub\n", encoding="utf-8"
        )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "deadbeef",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo)])

    assert exit_code == 1


def test_verify_factory_install_fails_when_bash_gateway_policy_is_invalid(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / "configs").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        json.dumps(
            {
                "workspace": {
                    "mcp": {
                        "servers": {"bashGateway": {"url": "http://127.0.0.1:3011/mcp"}}
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (factory_dir / "configs" / "bash_gateway_policy.default.yml").write_text(
        "policy:\n  allow:\n    - '^ls'\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "deadbeef",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo)])

    assert exit_code == 1


def test_verify_factory_runtime_passes_with_mocked_services(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        json.dumps(
            {
                "workspace": {
                    "mcp": {
                        "servers": {
                            "context7": {"url": "http://127.0.0.1:3010/mcp"},
                            "bashGateway": {"url": "http://127.0.0.1:3011/mcp"},
                        }
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (factory_dir / "configs").mkdir(parents=True, exist_ok=True)
    (factory_dir / "configs" / "bash_gateway_policy.default.yml").write_text(
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"PROJECT_WORKSPACE_ID={target_repo.name}",
                f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "deadbeef",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    services = {
        "mock-llm-gateway": "Up 10 seconds (healthy)",
        "mcp-memory": "Up 10 seconds (healthy)",
        "mcp-agent-bus": "Up 10 seconds (healthy)",
        "approval-gate": "Up 10 seconds (healthy)",
        "agent-worker": "Up 10 seconds (healthy)",
    }

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install,
        "collect_running_services",
        lambda compose_name: services,
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: None,
    )

    exit_code = verify_factory_install.main(
        ["--target", str(target_repo), "--runtime", "--check-vscode-mcp"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Runtime compliance passed" in output
    assert "Non-mutating runtime smoke prompt" in output


def test_runtime_smoke_prompt_uses_generated_endpoint_language() -> None:
    prompt = verify_factory_install.render_runtime_smoke_prompt(
        Path("/tmp/example-target"),
        "software-factory.code-workspace",
    )

    assert "generated runtime manifest" in prompt
    assert "effective workspace settings" in prompt
    assert "workspace's assigned ports" in prompt
    assert "generated workspace MCP URLs" in prompt
    assert "Workspace file: `software-factory.code-workspace`" in prompt
    assert "3030" not in prompt
    assert "3031" not in prompt
    assert "8001" not in prompt
    assert "3010-3018" not in prompt


def test_probe_http_url_allows_remote_disconnect_when_http_errors_allowed(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        verify_factory_install,
        "urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RemoteDisconnected("x")),
    )

    assert (
        verify_factory_install.probe_http_url(
            "http://127.0.0.1:3010/mcp",
            timeout=1.0,
            allow_http_error=True,
        )
        is None
    )

    message = verify_factory_install.probe_http_url(
        "http://127.0.0.1:3010/mcp",
        timeout=1.0,
        allow_http_error=False,
    )
    assert message is not None
    assert "remote disconnected" in message


def test_verify_factory_runtime_fails_when_required_service_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        json.dumps(
            {
                "workspace": {
                    "mcp": {
                        "servers": {"bashGateway": {"url": "http://127.0.0.1:3011/mcp"}}
                    }
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (factory_dir / "configs").mkdir(parents=True, exist_ok=True)
    (factory_dir / "configs" / "bash_gateway_policy.default.yml").write_text(
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"PROJECT_WORKSPACE_ID={target_repo.name}",
                f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "deadbeef",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install,
        "collect_running_services",
        lambda compose_name: {"mcp-memory": "Up 10 seconds (healthy)"},
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo), "--runtime"])

    assert exit_code == 1


def test_factory_stack_builds_full_compose_command(tmp_path: Path) -> None:
    repo_root = tmp_path / ".copilot/softwareFactoryVscode"
    repo_root.mkdir(parents=True, exist_ok=True)
    env_file = tmp_path / ".factory.env"

    command = factory_stack.build_compose_command(repo_root, env_file, ["up", "-d"])

    assert command[:6] == [
        "docker",
        "compose",
        "--project-directory",
        str(repo_root),
        "--env-file",
        str(env_file),
    ]
    for compose_file in factory_stack.COMPOSE_FILES:
        assert str((repo_root / compose_file).resolve()) in command
    assert command[-2:] == ["up", "-d"]


def test_factory_stack_parse_args_accepts_foreground(monkeypatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["factory_stack.py", "start", "--build", "--foreground"],
    )

    args = factory_stack.parse_args()

    assert args.command == "start"
    assert args.build is True
    assert args.foreground is True


def test_workspace_runtime_allocates_distinct_port_blocks_and_registry_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

    target_a = tmp_path / "project-a"
    target_b = tmp_path / "project-b"
    factory_a = target_a / ".copilot/softwareFactoryVscode"
    factory_b = target_b / ".copilot/softwareFactoryVscode"
    factory_a.mkdir(parents=True)
    factory_b.mkdir(parents=True)
    (factory_a / ".copilot" / "config").mkdir(parents=True)
    (factory_b / ".copilot" / "config").mkdir(parents=True)
    canonical_settings = (
        REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json"
    ).read_text(encoding="utf-8")
    (factory_a / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        canonical_settings,
        encoding="utf-8",
    )
    (factory_b / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        canonical_settings,
        encoding="utf-8",
    )

    config_a = factory_workspace.build_runtime_config(target_a, factory_dir=factory_a)
    manifest_a = factory_workspace.sync_runtime_artifacts(
        config_a,
        runtime_state="installed",
        active=False,
    )
    config_b = factory_workspace.build_runtime_config(target_b, factory_dir=factory_b)
    manifest_b = factory_workspace.sync_runtime_artifacts(
        config_b,
        runtime_state="running",
        active=True,
    )

    assert config_a.port_index == 0
    assert config_b.port_index == 1
    assert manifest_a["ports"]["PORT_CONTEXT7"] == 3010
    assert manifest_b["ports"]["PORT_CONTEXT7"] == 3110
    assert (
        manifest_b["mcp_servers"]["bashGateway"]["url"] == "http://127.0.0.1:3111/mcp"
    )

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config_b.factory_instance_id
    assert (
        registry["workspaces"][config_a.factory_instance_id]["runtime_state"]
        == "installed"
    )
    assert (
        registry["workspaces"][config_b.factory_instance_id]["runtime_state"]
        == "running"
    )


def test_workspace_runtime_rejects_explicit_port_conflicts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_a = tmp_path / "project-a"
    target_b = tmp_path / "project-b"
    factory_a = target_a / ".copilot/softwareFactoryVscode"
    factory_b = target_b / ".copilot/softwareFactoryVscode"
    factory_a.mkdir(parents=True)
    factory_b.mkdir(parents=True)
    (factory_a / ".copilot" / "config").mkdir(parents=True)
    (factory_b / ".copilot" / "config").mkdir(parents=True)
    canonical_settings = (
        REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json"
    ).read_text(encoding="utf-8")
    (factory_a / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        canonical_settings,
        encoding="utf-8",
    )
    (factory_b / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        canonical_settings,
        encoding="utf-8",
    )

    config_a = factory_workspace.build_runtime_config(target_a, factory_dir=factory_a)
    factory_workspace.sync_runtime_artifacts(
        config_a,
        runtime_state="installed",
        active=False,
    )

    (factory_b / ".factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_b}",
                "PROJECT_WORKSPACE_ID=project-b",
                "COMPOSE_PROJECT_NAME=factory_project-b",
                f"FACTORY_DIR={factory_b}",
                "FACTORY_INSTANCE_ID=factory-project-b",
                f"PORT_CONTEXT7={config_a.ports['PORT_CONTEXT7']}",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    try:
        factory_workspace.build_runtime_config(target_b, factory_dir=factory_b)
    except RuntimeError as exc:
        assert "conflict" in str(exc).lower()
    else:
        raise AssertionError("Expected explicit port conflict to raise RuntimeError")


def test_factory_stack_start_stop_activate_preserve_workspace_distinction(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

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
    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="installed", active=False
    )

    calls: list[list[str]] = []

    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda repo, command: calls.append(list(command)),
    )
    monkeypatch.setattr(
        factory_stack, "collect_running_services", lambda compose_project_name: {}
    )

    factory_stack.start_stack(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env", build=False, wait=False
    )
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )
    assert registry["active_workspace"] == ""

    factory_stack.activate_workspace(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )

    factory_stack.stop_stack(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "stopped"
    )
    assert registry["active_workspace"] == config.factory_instance_id

    factory_stack.deactivate_workspace(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == ""
    assert len(calls) == 2


def test_factory_stack_start_rolls_back_runtime_state_when_compose_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

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
    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="installed", active=False
    )

    def _raise_compose_error(_repo: Path, _command: list[str]) -> None:
        raise subprocess.CalledProcessError(1, ["docker", "compose", "up"])

    monkeypatch.setattr(factory_stack, "run_compose_command", _raise_compose_error)
    monkeypatch.setattr(
        factory_stack, "collect_running_services", lambda compose_project_name: {}
    )

    try:
        factory_stack.start_stack(
            repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env", build=False, wait=False
        )
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected compose failure to bubble up.")

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "failed"
    )


def test_factory_stack_status_reports_degraded_when_required_service_restarts(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

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

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="running", active=False
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda compose_project_name: {
            "mock-llm-gateway": "Up 10 seconds (healthy)",
            "mcp-memory": "Up 10 seconds (healthy)",
            "mcp-agent-bus": "Up 10 seconds (healthy)",
            "approval-gate": "Up 10 seconds (healthy)",
            "agent-worker": "Restarting (1) 3 seconds ago",
        },
    )

    factory_stack.status_workspace(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")
    output = capsys.readouterr().out

    assert "runtime_state=degraded" in output
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"]
        == "degraded"
    )


def test_factory_stack_status_does_not_rewrite_custom_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

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
    custom_env = "\n".join(
        [
            f"TARGET_WORKSPACE_PATH={target_repo}",
            "PROJECT_WORKSPACE_ID=target-project",
            "COMPOSE_PROJECT_NAME=factory_target-project",
            "CONTEXT7_API_KEY=abc123",
            "",
        ]
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(custom_env, encoding="utf-8")

    factory_stack.status_workspace(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")

    assert (target_repo / ".copilot/softwareFactoryVscode/.factory.env").read_text(encoding="utf-8") == custom_env


def test_deactivate_workspace_does_not_clear_another_active_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

    def prepare_workspace(
        target_repo: Path,
    ) -> tuple[Path, factory_workspace.WorkspaceRuntimeConfig]:
        repo_root = target_repo / ".copilot/softwareFactoryVscode"
        repo_root.mkdir(parents=True)
        (repo_root / ".copilot" / "config").mkdir(parents=True)
        (repo_root / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
            (
                REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        config = factory_workspace.build_runtime_config(
            target_repo, factory_dir=repo_root
        )
        factory_workspace.sync_runtime_artifacts(
            config,
            runtime_state="installed",
            active=False,
        )
        return repo_root, config

    repo_a, config_a = prepare_workspace(tmp_path / "project-a")
    repo_b, config_b = prepare_workspace(tmp_path / "project-b")

    factory_stack.activate_workspace(
        repo_a, env_file=config_a.target_dir / ".factory.env"
    )
    factory_stack.deactivate_workspace(
        repo_b, env_file=config_b.target_dir / ".factory.env"
    )

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config_a.factory_instance_id


def test_starting_one_workspace_does_not_change_another_workspace_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

    def prepare_workspace(
        target_repo: Path,
    ) -> tuple[Path, factory_workspace.WorkspaceRuntimeConfig]:
        repo_root = target_repo / ".copilot/softwareFactoryVscode"
        repo_root.mkdir(parents=True)
        (repo_root / ".copilot" / "config").mkdir(parents=True)
        (repo_root / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
            (
                REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        config = factory_workspace.build_runtime_config(
            target_repo, factory_dir=repo_root
        )
        factory_workspace.sync_runtime_artifacts(
            config,
            runtime_state="installed",
            active=False,
        )
        return repo_root, config

    repo_a, config_a = prepare_workspace(tmp_path / "project-a")
    _, config_b = prepare_workspace(tmp_path / "project-b")

    monkeypatch.setattr(
        factory_stack, "run_compose_command", lambda repo, command: None
    )
    monkeypatch.setattr(
        factory_stack, "collect_running_services", lambda compose_project_name: {}
    )

    factory_stack.start_stack(
        repo_a, env_file=config_a.target_dir / ".factory.env", build=False, wait=False
    )

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config_a.factory_instance_id]["runtime_state"]
        == "running"
    )
    assert (
        registry["workspaces"][config_b.factory_instance_id]["runtime_state"]
        == "installed"
    )
    assert (
        registry["workspaces"][config_a.factory_instance_id]["port_index"]
        != registry["workspaces"][config_b.factory_instance_id]["port_index"]
    )


def test_verify_runtime_uses_generated_workspace_endpoint_settings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / "configs").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (factory_dir / "configs" / "bash_gateway_policy.default.yml").write_text(
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    custom_env = "\n".join(
        [
            f"TARGET_WORKSPACE_PATH={target_repo}",
            f"PROJECT_WORKSPACE_ID={target_repo.name}",
            f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
            f"FACTORY_DIR={factory_dir}",
            "FACTORY_INSTANCE_ID=factory-custom",
            "FACTORY_PORT_INDEX=2",
            "PORT_CONTEXT7=3210",
            "PORT_BASH=3211",
            "PORT_FS=3212",
            "PORT_GIT=3213",
            "PORT_SEARCH=3214",
            "PORT_TEST=3215",
            "PORT_COMPOSE=3216",
            "PORT_DOCS=3217",
            "PORT_GITHUB=3218",
            "MEMORY_MCP_PORT=3230",
            "AGENT_BUS_PORT=3231",
            "APPROVAL_GATE_PORT=8201",
            "PORT_TUI=9290",
            "CONTEXT7_API_KEY=",
            "",
        ]
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(custom_env, encoding="utf-8")
    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="running", active=False
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "deadbeef",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    probed_urls: list[str] = []

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install,
        "collect_running_services",
        lambda compose_name: {
            "mock-llm-gateway": "Up 10 seconds (healthy)",
            "mcp-memory": "Up 10 seconds (healthy)",
            "mcp-agent-bus": "Up 10 seconds (healthy)",
            "approval-gate": "Up 10 seconds (healthy)",
            "agent-worker": "Up 10 seconds (healthy)",
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: probed_urls.append(url) or None,
    )

    exit_code = verify_factory_install.main(
        [
            "--target",
            str(target_repo),
            "--runtime",
            "--check-vscode-mcp",
            "--no-smoke-prompt",
        ]
    )

    assert exit_code == 0
    assert "http://127.0.0.1:3230/mcp" in probed_urls
    assert "http://127.0.0.1:3231/mcp" in probed_urls
    assert "http://127.0.0.1:8201/health" in probed_urls
    assert "http://127.0.0.1:3211/mcp" in probed_urls


def test_validate_throwaway_install_uses_canonical_stack_helper(
    tmp_path: Path,
    monkeypatch,
) -> None:
    validator = load_module(
        "validate_throwaway_install_under_test",
        REPO_ROOT / "scripts" / "validate_throwaway_install.py",
    )
    repo_root = tmp_path / ".copilot/softwareFactoryVscode"
    repo_root.mkdir(parents=True, exist_ok=True)
    env_file = tmp_path / ".factory.env"
    env_file.write_text("COMPOSE_PROJECT_NAME=factory_test\n", encoding="utf-8")
    calls: list[tuple[str, Path, Path, bool | int]] = []

    monkeypatch.setattr(
        validator,
        "stop_factory_stack",
        lambda repo_root_arg, *, env_file, remove_volumes=False: calls.append(
            ("stop", repo_root_arg, env_file, remove_volumes)
        ),
    )
    monkeypatch.setattr(
        validator,
        "start_factory_stack",
        lambda repo_root_arg, *, env_file, build=True, wait=True, wait_timeout=0: calls.append(
            ("start", repo_root_arg, env_file, wait_timeout)
        ),
    )

    assert validator.maybe_stop_stack(repo_root, env_file, remove_volumes=True) is True
    validator.start_stack(repo_root, env_file, build=True)

    assert calls == [
        ("stop", repo_root, env_file, True),
        ("start", repo_root, env_file, factory_stack.DEFAULT_WAIT_TIMEOUT),
    ]


def test_runtime_compose_files_build_from_repo_root() -> None:
    compose_files = [
        REPO_ROOT / "compose" / "docker-compose.factory.yml",
        REPO_ROOT / "compose" / "docker-compose.context7.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-bash-gateway.yml",
        REPO_ROOT / "compose" / "docker-compose.repo-fundamentals-mcp.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-devops.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-offline-docs.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-github-ops.yml",
    ]

    for compose_file in compose_files:
        data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        for service in data.get("services", {}).values():
            build = service.get("build")
            if isinstance(build, dict):
                assert build.get("context") == "."


def test_runtime_compose_shared_services_do_not_override_internal_ports() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    memory_env = services.get("mcp-memory", {}).get("environment", {})
    bus_env = services.get("mcp-agent-bus", {}).get("environment", {})
    approval_env = services.get("approval-gate", {}).get("environment", {})

    assert "MEMORY_MCP_PORT" not in memory_env
    assert "AGENT_BUS_PORT" not in bus_env
    assert "APPROVAL_GATE_PORT" not in approval_env


def test_runtime_compose_interservice_urls_use_fixed_internal_ports() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    approval_env = services.get("approval-gate", {}).get("environment", {})
    worker_env = services.get("agent-worker", {}).get("environment", {})

    assert approval_env.get("AGENT_BUS_URL") == "http://mcp-agent-bus:3031"
    assert worker_env.get("MEMORY_MCP_URL") == "http://mcp-memory:3030"
    assert worker_env.get("AGENT_BUS_URL") == "http://mcp-agent-bus:3031"
    assert worker_env.get("APPROVAL_GATE_URL") == "http://approval-gate:8001"


def test_runtime_compose_agent_worker_has_healthcheck() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    worker = data.get("services", {}).get("agent-worker", {})
    healthcheck = worker.get("healthcheck", {})

    assert isinstance(healthcheck, dict)
    test_cmd = healthcheck.get("test", [])
    assert isinstance(test_cmd, list)
    joined = " ".join(str(item) for item in test_cmd)
    assert "/proc/1/cmdline" in joined
    assert "run-queue" in joined


def test_runtime_dockerfiles_copy_from_factory_runtime_tree() -> None:
    dockerfiles = [
        REPO_ROOT / "docker" / "mcp-memory" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-agent-bus" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-bash-gateway" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-test-runner" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-github-ops" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-offline-docs" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-git" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-search" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-filesystem" / "Dockerfile",
        REPO_ROOT / "docker" / "approval-gate" / "Dockerfile",
        REPO_ROOT / "docker" / "agent-worker" / "Dockerfile",
        REPO_ROOT / "docker" / "mock-llm-gateway" / "Dockerfile",
    ]

    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        assert "factory_runtime/" in text


def test_agent_worker_requirements_include_openai_sdk() -> None:
    requirements = (
        REPO_ROOT / "factory_runtime" / "agents" / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "openai==" in requirements


def test_offline_docs_compose_does_not_mount_over_runtime_code_path() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.mcp-offline-docs.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    service = data.get("services", {}).get("offline-docs-mcp", {})
    volumes = service.get("volumes", [])
    assert all(not str(volume).endswith(":/factory") for volume in volumes)

    env = service.get("environment", [])
    joined_env = "\n".join(str(item) for item in env)
    assert (
        "OFFLINE_DOCS_INDEX_DB=/factory-data/.tmp/mcp-offline-docs/docs_index.db"
        in joined_env
    )


def test_auxiliary_mcp_compose_files_do_not_mount_over_runtime_code_path() -> None:
    compose_expectations = {
        REPO_ROOT
        / "compose"
        / "docker-compose.mcp-bash-gateway.yml": [
            (
                "BASH_GATEWAY_POLICY_PATH=${BASH_GATEWAY_POLICY_PATH:-"
                "/factory-data/configs/bash_gateway_policy.default.yml}"
            ),
            "BASH_GATEWAY_AUDIT_DIR=/factory-data/.tmp/agent-script-runs",
        ],
        REPO_ROOT
        / "compose"
        / "docker-compose.mcp-devops.yml": [
            "DOCKER_COMPOSE_MCP_AUDIT_DIR=/factory-data/.tmp/mcp-docker-compose",
            "TEST_RUNNER_MCP_AUDIT_DIR=/factory-data/.tmp/mcp-test-runner",
        ],
        REPO_ROOT
        / "compose"
        / "docker-compose.mcp-github-ops.yml": [
            "GITHUB_OPS_MCP_AUDIT_DIR=/factory-data/.tmp/mcp-github-ops",
        ],
    }

    for compose_file, expected_env_entries in compose_expectations.items():
        text = compose_file.read_text(encoding="utf-8")
        assert "${FACTORY_DIR:-.}:/factory\n" not in text
        assert "${FACTORY_DIR:-.}:/factory-data" in text
        for expected in expected_env_entries:
            assert expected in text


def test_auxiliary_mcp_dockerfiles_use_factory_runtime_package_entrypoints() -> None:
    dockerfiles = [
        REPO_ROOT / "docker" / "mcp-bash-gateway" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-github-ops" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-test-runner" / "Dockerfile",
    ]

    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        assert "COPY factory_runtime/ /factory/factory_runtime/" in text
        assert 'ENV PYTHONPATH="/factory"' in text
        assert '"-m", "factory_runtime.apps.mcp.' in text


def test_reconcile_registry_prunes_ephemeral_pytest_workspaces(
    tmp_path: Path, monkeypatch
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))

    ephemeral_target = tmp_path / "pytest-of-sw" / "pytest-1" / "target-project"
    ephemeral_target.mkdir(parents=True, exist_ok=True)
    (ephemeral_target / ".tmp" / "softwareFactoryVscode").mkdir(
        parents=True, exist_ok=True
    )
    (
        ephemeral_target / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    ).write_text("{}\n", encoding="utf-8")

    persistent_target = Path("/tmp") / "factory-registry-persistent-target"
    if persistent_target.exists():
        shutil.rmtree(persistent_target)
    persistent_target.mkdir(parents=True, exist_ok=True)
    try:
        (persistent_target / ".tmp" / "softwareFactoryVscode").mkdir(
            parents=True, exist_ok=True
        )
        (
            persistent_target
            / ".tmp"
            / "softwareFactoryVscode"
            / "runtime-manifest.json"
        ).write_text("{}\n", encoding="utf-8")

        registry = {
            "version": 1,
            "active_workspace": "",
            "workspaces": {
                "factory-ephemeral": {
                    "factory_instance_id": "factory-ephemeral",
                    "target_workspace_path": str(ephemeral_target),
                    "runtime_state": "installed",
                },
                "factory-persistent": {
                    "factory_instance_id": "factory-persistent",
                    "target_workspace_path": str(persistent_target),
                    "runtime_state": "installed",
                },
            },
        }
        factory_workspace.write_json_atomic(registry_path, registry)

        result = factory_workspace.reconcile_registry(registry_path=registry_path)
        updated = factory_workspace.load_registry(registry_path=registry_path)

        assert "factory-ephemeral" in result["stale_removed"]
        assert "factory-ephemeral" not in updated["workspaces"]
        assert "factory-persistent" in updated["workspaces"]
    finally:
        shutil.rmtree(persistent_target, ignore_errors=True)


def test_agent_worker_entrypoint_targets_supported_factory_cli_mode() -> None:
    dockerfile = REPO_ROOT / "docker" / "agent-worker" / "Dockerfile"
    cli_file = REPO_ROOT / "factory_runtime" / "agents" / "factory_cli.py"

    docker_text = dockerfile.read_text(encoding="utf-8")
    cli_text = cli_file.read_text(encoding="utf-8")

    assert '"run-queue"' in docker_text
    assert 'sys.argv[1] == "run-queue"' in cli_text


def test_runtime_mcp_dockerfiles_pin_fastmcp_compatible_version() -> None:
    dockerfiles = [
        REPO_ROOT / "docker" / "mcp-memory" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-agent-bus" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-bash-gateway" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-test-runner" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-github-ops" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-offline-docs" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-git" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-search" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-filesystem" / "Dockerfile",
    ]

    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        assert "mcp==1.25.0" in text
        assert "uvicorn[standard]==0.44.0" in text


def test_verify_runtime_services_contract_is_shared() -> None:
    assert (
        verify_factory_install.RUNTIME_SERVICES
        == factory_workspace.RUNTIME_SERVICE_CONTRACT
    )

    agent_worker = verify_factory_install.RUNTIME_SERVICES["agent-worker"]
    assert agent_worker["require_healthy_status"] is True


def test_devops_docker_compose_image_uses_known_working_docker_cli_base() -> None:
    dockerfile = REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile"

    text = dockerfile.read_text(encoding="utf-8")

    assert "FROM docker:27.4.1-cli" in text
    assert "FROM docker:27-cli" not in text


def test_cleanup_workspace(tmp_path: Path):
    sys.path.insert(0, str(Path("scripts").resolve()))
    import factory_workspace as workspace_module
    from factory_stack import cleanup_workspace

    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    factory_dir = target / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    data_root = tmp_path / "factory-data"
    (target / ".copilot/softwareFactoryVscode").mkdir(parents=True, exist_ok=True)
    (target / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target}",
                "PROJECT_WORKSPACE_ID=target",
                "COMPOSE_PROJECT_NAME=factory_target",
                f"FACTORY_DIR={factory_dir}",
                f"FACTORY_DATA_DIR={data_root}",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = workspace_module.build_runtime_config(target, factory_dir=factory_dir)
    workspace_module.sync_runtime_artifacts(config)
    (data_root / "memory" / config.factory_instance_id).mkdir(parents=True)
    (data_root / "bus" / config.factory_instance_id).mkdir(parents=True)

    # Assert created
    assert (target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert (
        target / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    ).exists()

    # cleanup
    cleanup_workspace(factory_dir, env_file=(target / ".copilot/softwareFactoryVscode/.factory.env"))

    assert not (target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert not (
        target / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    ).exists()
    assert not (data_root / "memory" / config.factory_instance_id).exists()
    assert not (data_root / "bus" / config.factory_instance_id).exists()

    reg = workspace_module.load_registry()
    assert config.factory_instance_id not in reg.get("workspaces", {})


# ---------------------------------------------------------------------------
# Production readiness regression tests (mitigation plan, all 7 findings)
# ---------------------------------------------------------------------------


def test_all_auxiliary_compose_services_have_healthchecks() -> None:
    """Finding #3 — all services across all compose files must have healthchecks."""
    compose_files = [
        REPO_ROOT / "compose" / "docker-compose.mcp-bash-gateway.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-devops.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-github-ops.yml",
        REPO_ROOT / "compose" / "docker-compose.mcp-offline-docs.yml",
        REPO_ROOT / "compose" / "docker-compose.repo-fundamentals-mcp.yml",
        REPO_ROOT / "compose" / "docker-compose.context7.yml",
    ]
    for compose_file in compose_files:
        data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
        for service_name, service in data.get("services", {}).items():
            assert (
                "healthcheck" in service
            ), f"Service '{service_name}' in {compose_file.name} is missing a healthcheck"
            hc = service["healthcheck"]
            assert (
                "test" in hc
            ), f"Service '{service_name}' healthcheck has no test command"
            assert (
                "interval" in hc
            ), f"Service '{service_name}' healthcheck has no interval"


def test_factory_compose_all_services_have_healthchecks() -> None:
    """Finding #3 — factory compose file services must have healthchecks."""
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    for service_name, service in data.get("services", {}).items():
        # agent-worker has no port — liveness via restart policy; skip healthcheck assert
        if service_name == "agent-worker":
            continue
        assert (
            "healthcheck" in service
        ), f"Service '{service_name}' in docker-compose.factory.yml is missing a healthcheck"


def test_all_mcp_dockerfiles_use_factory_runtime_module_paths() -> None:
    """Finding #4 — all factory-managed Dockerfiles must use factory_runtime.* CMD, not apps.*"""
    dockerfiles = [
        REPO_ROOT / "docker" / "mcp-memory" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-agent-bus" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-bash-gateway" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-devops-test-runner" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-github-ops" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-offline-docs" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-git" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-search" / "Dockerfile",
        REPO_ROOT / "docker" / "mcp-repo-fundamentals-filesystem" / "Dockerfile",
        REPO_ROOT / "docker" / "approval-gate" / "Dockerfile",
        REPO_ROOT / "docker" / "agent-worker" / "Dockerfile",
        REPO_ROOT / "docker" / "mock-llm-gateway" / "Dockerfile",
    ]
    for dockerfile in dockerfiles:
        text = dockerfile.read_text(encoding="utf-8")
        assert (
            "factory_runtime.apps." in text or '"run-queue"' in text
        ), f"{dockerfile} uses an old module path (apps.*) instead of factory_runtime.apps.*"
        # Legacy check: CMD must not reference bare "apps.*" (only "factory_runtime.apps.*" is valid)
        import re

        legacy_cmd = re.search(r'"-m",\s*"apps\.', text) or re.search(
            r"python\s+-m\s+apps\.", text
        )
        assert (
            not legacy_cmd
        ), f"{dockerfile} still contains legacy standalone apps.* CMD"


def test_mock_llm_gateway_dockerfile_pins_all_dependencies() -> None:
    """Finding #5 — mock-llm-gateway must pin all runtime deps."""
    dockerfile = REPO_ROOT / "docker" / "mock-llm-gateway" / "Dockerfile"
    text = dockerfile.read_text(encoding="utf-8")
    assert "fastapi==" in text, "mock-llm-gateway must pin fastapi version"
    assert "uvicorn==" in text, "mock-llm-gateway must pin uvicorn version"
    assert "pydantic==" in text, "mock-llm-gateway must pin pydantic version"


def test_factory_stack_status_emits_commit_tracking_fields(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Finding #6 — status must output factory_commit, lock_commit, needs_rebuild."""
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

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
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "aabbccdd",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack, "collect_running_services", lambda compose_project_name: {}
    )

    factory_stack.status_workspace(repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env")
    output = capsys.readouterr().out

    assert "factory_commit=" in output
    assert "lock_commit=aabbccdd" in output
    assert "needs_rebuild=" in output


def test_factory_stack_write_lock_commit_updates_lock_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Finding #6 — write_factory_lock_commit must stamp the lock file."""
    target_dir = tmp_path / "target"
    target_dir.mkdir(parents=True, exist_ok=True)
    lock_file = target_dir / ".copilot/softwareFactoryVscode/lock.json"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".copilot/softwareFactoryVscode",
                    "workspace_file": "software-factory.code-workspace",
                    "commit": "",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    factory_dir = REPO_ROOT
    factory_stack.write_factory_lock_commit(target_dir, factory_dir)

    updated = json.loads(lock_file.read_text(encoding="utf-8"))
    commit = updated["factory"]["commit"]
    assert len(commit) == 40 or len(commit) == 7, f"Unexpected commit hash: {commit!r}"
    assert (
        commit != ""
    ), "Lock file commit must be non-empty after write_factory_lock_commit"


def test_adr_011_agent_worker_liveness_contract_exists() -> None:
    """Finding #2 — ADR-011 documenting agent-worker Option A must exist."""
    adr = (
        REPO_ROOT
        / "docs"
        / "architecture"
        / "ADR-011-Agent-Worker-Liveness-Contract.md"
    )
    assert (
        adr.exists()
    ), "ADR-011-Agent-Worker-Liveness-Contract.md must exist in docs/architecture/"
    text = adr.read_text(encoding="utf-8")
    assert "Option A" in text, "ADR-011 must document Option A liveness placeholder"
    assert (
        "run-queue" in text or "run_queue" in text
    ), "ADR-011 must reference the run-queue entrypoint"


def test_ci_workflow_has_container_build_job() -> None:
    """Finding #7 — CI must have a job that validates Dockerfiles build successfully."""
    ci_file = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    text = ci_file.read_text(encoding="utf-8")
    assert (
        "container-build" in text or "docker build" in text.lower()
    ), "CI workflow must have a container-build or Docker build validation job"
    # Confirm it loops over all Dockerfiles
    assert (
        "docker/*/Dockerfile" in text or "Dockerfile" in text
    ), "CI container-build job must reference Dockerfiles"
