from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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
    assert (target_repo / ".softwareFactoryVscode").exists()
    assert (target_repo / ".tmp" / "softwareFactoryVscode").exists()

    factory_env = (target_repo / ".factory.env").read_text(encoding="utf-8")
    assert f"TARGET_WORKSPACE_PATH={target_repo}" in factory_env
    assert f"FACTORY_DIR={target_repo / '.softwareFactoryVscode'}" in factory_env
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
    assert workspace["folders"][1]["path"] == ".softwareFactoryVscode"
    assert (
        workspace["settings"]["mcp"]["servers"]["bashGateway"]["url"]
        == f"http://127.0.0.1:{port_bash}/mcp"
    )

    lock_data = json.loads(
        (target_repo / ".factory.lock.json").read_text(encoding="utf-8")
    )
    assert lock_data["version"] == "main"
    assert lock_data["factory"]["repo_url"] == str(source_repo)
    assert lock_data["factory"]["workspace_file"] == "software-factory.code-workspace"
    assert lock_data["factory"]["commit"]

    gitignore = (target_repo / ".gitignore").read_text(encoding="utf-8")
    assert ".tmp/softwareFactoryVscode/" in gitignore
    assert ".factory.env" in gitignore


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

    factory_dir = target_repo / ".softwareFactoryVscode"
    assert factory_dir.is_dir()
    assert (factory_dir / ".git").exists()
    assert (factory_dir / "setup.sh").exists()
    assert (factory_dir / ".venv" / "bin" / "python").exists()
    assert (target_repo / ".tmp" / "softwareFactoryVscode").is_dir()
    assert (
        target_repo / ".tmp" / "softwareFactoryVscode" / "runtime-manifest.json"
    ).is_file()
    assert (target_repo / ".factory.env").is_file()
    assert (target_repo / ".factory.lock.json").is_file()
    assert (target_repo / "software-factory.code-workspace").is_file()
    assert (
        target_repo
        / ".softwareFactoryVscode"
        / "configs"
        / "bash_gateway_policy.default.yml"
    ).is_file()
    assert (
        target_repo
        / ".softwareFactoryVscode"
        / ".copilot"
        / "config"
        / "vscode-agent-settings.json"
    ).is_file()

    lock_data = json.loads(
        (target_repo / ".factory.lock.json").read_text(encoding="utf-8")
    )
    assert lock_data["factory"]["repo_url"] == str(source_repo)
    assert lock_data["factory"]["install_path"] == ".softwareFactoryVscode"
    assert lock_data["factory"]["workspace_file"] == "software-factory.code-workspace"
    assert lock_data["factory"]["commit"]

    workspace_data = json.loads(
        (target_repo / "software-factory.code-workspace").read_text(encoding="utf-8")
    )
    assert workspace_data["folders"] == [
        {"name": "Host Project (Root)", "path": "."},
        {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
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
        / ".softwareFactoryVscode"
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
    custom_workspace = (
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
                ],
                "settings": {"custom": True},
            },
            indent=2,
        )
        + "\n"
    )
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
    (target_repo / ".factory.env").write_text(custom_env, encoding="utf-8")

    assert (
        install_factory.main(
            ["--target", str(target_repo), "--repo-url", str(source_repo), "--update"]
        )
        == 0
    )

    assert workspace_path.read_text(encoding="utf-8") == custom_workspace
    updated_env = (target_repo / ".factory.env").read_text(encoding="utf-8")
    assert "CONTEXT7_API_KEY=abc123" in updated_env
    assert "PORT_BASH=" in updated_env


def test_bootstrap_force_workspace_overwrites_existing_workspace(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    (target_repo / ".softwareFactoryVscode").mkdir()
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
    assert generated["folders"][1]["path"] == ".softwareFactoryVscode"


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
    (target_repo / ".softwareFactoryVscode").mkdir()
    (target_repo / ".softwareFactoryVscode" / ".git").mkdir()
    (target_repo / ".softwareFactoryVscode" / "scripts").mkdir()
    for script_name in (
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (target_repo / ".softwareFactoryVscode" / "scripts" / script_name).write_text(
            "# stub\n", encoding="utf-8"
        )
    (target_repo / ".factory.env").write_text(
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
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".factory.lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".softwareFactoryVscode",
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
    factory_dir = target_repo / ".softwareFactoryVscode"
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
    (target_repo / ".factory.env").write_text(
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
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".factory.lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".softwareFactoryVscode",
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
                    {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
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
    factory_dir = target_repo / ".softwareFactoryVscode"
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
    (target_repo / ".factory.env").write_text(
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
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".factory.lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".softwareFactoryVscode",
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
                    {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
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
        "agent-worker": "Up 10 seconds",
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


def test_verify_factory_runtime_fails_when_required_service_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".softwareFactoryVscode"
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
    (target_repo / ".factory.env").write_text(
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
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".factory.lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".softwareFactoryVscode",
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
                    {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
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


def test_factory_stack_resolves_env_file_from_repo_or_parent(tmp_path: Path) -> None:
    repo_root = tmp_path / ".softwareFactoryVscode"
    repo_root.mkdir(parents=True, exist_ok=True)

    local_env = repo_root / ".factory.env"
    local_env.write_text("COMPOSE_PROJECT_NAME=factory_local\n", encoding="utf-8")
    assert factory_stack.resolve_env_file(repo_root) == local_env.resolve()

    local_env.unlink()
    parent_env = tmp_path / ".factory.env"
    parent_env.write_text("COMPOSE_PROJECT_NAME=factory_parent\n", encoding="utf-8")
    assert factory_stack.resolve_env_file(repo_root) == parent_env.resolve()


def test_factory_stack_builds_full_compose_command(tmp_path: Path) -> None:
    repo_root = tmp_path / ".softwareFactoryVscode"
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
    factory_a = target_a / ".softwareFactoryVscode"
    factory_b = target_b / ".softwareFactoryVscode"
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
    factory_a = target_a / ".softwareFactoryVscode"
    factory_b = target_b / ".softwareFactoryVscode"
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

    (target_b / ".factory.env").write_text(
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
    repo_root = target_repo / ".softwareFactoryVscode"
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
        repo_root, env_file=target_repo / ".factory.env", build=False, wait=False
    )
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )
    assert registry["active_workspace"] == ""

    factory_stack.activate_workspace(repo_root, env_file=target_repo / ".factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )

    factory_stack.stop_stack(repo_root, env_file=target_repo / ".factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "stopped"
    )
    assert registry["active_workspace"] == config.factory_instance_id

    factory_stack.deactivate_workspace(repo_root, env_file=target_repo / ".factory.env")
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == ""
    assert len(calls) == 2


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
    repo_root = target_repo / ".softwareFactoryVscode"
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
    (target_repo / ".factory.env").write_text(custom_env, encoding="utf-8")

    factory_stack.status_workspace(repo_root, env_file=target_repo / ".factory.env")

    assert (target_repo / ".factory.env").read_text(encoding="utf-8") == custom_env


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
        repo_root = target_repo / ".softwareFactoryVscode"
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
        repo_root = target_repo / ".softwareFactoryVscode"
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
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".softwareFactoryVscode"
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
    (target_repo / ".factory.env").write_text(custom_env, encoding="utf-8")
    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="running", active=False
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.tmp/softwareFactoryVscode/\n.factory.env\n",
        encoding="utf-8",
    )
    (target_repo / ".factory.lock.json").write_text(
        json.dumps(
            {
                "version": "main",
                "installed_at": "2026-03-21T00:00:00Z",
                "updated_at": "2026-03-21T00:00:00Z",
                "factory": {
                    "repo_url": "https://example.invalid/factory.git",
                    "install_path": ".softwareFactoryVscode",
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
                    {"name": "AI Agent Factory", "path": ".softwareFactoryVscode"},
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
            "agent-worker": "Up 10 seconds",
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
    assert "http://127.0.0.1:3230/health" in probed_urls
    assert "http://127.0.0.1:3231/health" in probed_urls
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
    repo_root = tmp_path / ".softwareFactoryVscode"
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


def test_devops_docker_compose_image_uses_known_working_docker_cli_base() -> None:
    dockerfile = REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile"

    text = dockerfile.read_text(encoding="utf-8")

    assert "FROM docker:27.4.1-cli" in text
    assert "FROM docker:27-cli" not in text
