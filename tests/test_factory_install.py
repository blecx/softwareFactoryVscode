from __future__ import annotations

import asyncio
import importlib.util
import json
import shutil
import subprocess
import sys
from http.client import RemoteDisconnected
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_VERSION = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
INSTALL_SCRIPT = REPO_ROOT / "scripts" / "install_factory.py"
BOOTSTRAP_SCRIPT = REPO_ROOT / "scripts" / "bootstrap_host.py"
FACTORY_RELEASE_SCRIPT = REPO_ROOT / "scripts" / "factory_release.py"
FACTORY_UPDATE_SCRIPT = REPO_ROOT / "scripts" / "factory_update.py"
VERIFY_RELEASE_DOCS_SCRIPT = REPO_ROOT / "scripts" / "verify_release_docs.py"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify_factory_install.py"
FACTORY_STACK_SCRIPT = REPO_ROOT / "scripts" / "factory_stack.py"
FACTORY_WORKSPACE_SCRIPT = REPO_ROOT / "scripts" / "factory_workspace.py"
WORKSPACE_TEMPLATE = REPO_ROOT / "workspace.code-workspace.template"
ROOT_GITIGNORE = REPO_ROOT / ".gitignore"


def load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


install_factory = load_module("install_factory_under_test", INSTALL_SCRIPT)
bootstrap_host = load_module("bootstrap_host_under_test", BOOTSTRAP_SCRIPT)
factory_release = load_module("factory_release_under_test", FACTORY_RELEASE_SCRIPT)
factory_update = load_module("factory_update_under_test", FACTORY_UPDATE_SCRIPT)
verify_release_docs = load_module(
    "verify_release_docs_under_test", VERIFY_RELEASE_DOCS_SCRIPT
)
verify_factory_install = load_module("verify_factory_install_under_test", VERIFY_SCRIPT)
factory_stack = load_module("factory_stack_under_test", FACTORY_STACK_SCRIPT)
factory_workspace = load_module(
    "factory_workspace_under_test", FACTORY_WORKSPACE_SCRIPT
)
factory_agents = load_module(
    "factory_agents_under_test",
    REPO_ROOT / "factory_runtime" / "agents" / "factory.py",
)
mcp_lifecycle = load_module(
    "mcp_lifecycle_under_test",
    REPO_ROOT / "factory_runtime" / "agents" / "mcp_lifecycle.py",
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
            "image": "factory_context7",
            "published_ports": [config.ports["PORT_CONTEXT7"]],
        },
        "bash-gateway-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_bash",
            "published_ports": [config.ports["PORT_BASH"]],
        },
        "git-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_git",
            "published_ports": [config.ports["PORT_FS"]],
        },
        "search-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_search",
            "published_ports": [config.ports["PORT_GIT"]],
        },
        "filesystem-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_fs",
            "published_ports": [config.ports["PORT_SEARCH"]],
        },
        "docker-compose-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_compose",
            "published_ports": [config.ports["PORT_COMPOSE"]],
        },
        "test-runner-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_test",
            "published_ports": [config.ports["PORT_TEST"]],
        },
        "offline-docs-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_docs",
            "published_ports": [config.ports["PORT_DOCS"]],
        },
        "github-ops-mcp": {
            "status": "Up 10 seconds (healthy)",
            "image": "factory_github",
            "published_ports": [config.ports["PORT_GITHUB"]],
        },
    }


def stub_runtime_manager_with_successful_probes(
    monkeypatch,
    stack_module: Any,
    *,
    registry_path: Path | None = None,
) -> None:
    monkeypatch.setattr(
        stack_module,
        "build_runtime_manager",
        lambda workspace_file=stack_module.DEFAULT_WORKSPACE_FILENAME: stack_module.MCPRuntimeManager(
            registry_path=registry_path,
            default_workspace_file=workspace_file,
            docker_available_checker=lambda: True,
            service_inventory_loader=stack_module.collect_service_inventory,
            stack_module_loader=lambda: stack_module,
            http_probe_func=lambda url, timeout, allow_http_error: None,
            mcp_initialize_probe=lambda url, timeout, workspace_id: None,
        ),
    )


def build_snapshot_service_record(
    *,
    workspace_owned: bool = True,
    status: str = "running",
    docker_status: str = "Up 10 seconds (healthy)",
    probe_url: str = "",
    details: tuple[str, ...] = (),
) -> Any:
    return SimpleNamespace(
        workspace_owned=workspace_owned,
        status=SimpleNamespace(value=status),
        docker_status=docker_status,
        probe_url=probe_url,
        details=details,
    )


def build_runtime_snapshot_contract(
    *,
    lifecycle_state: Any | None = None,
    persisted_runtime_state: str = "running",
    readiness_status: str = "ready",
    recommended_action: str = "none",
    ready: bool = True,
    reason_codes: tuple[str, ...] = (),
    issues: tuple[str, ...] = (),
    compose_project_name: str = "factory_target-project",
    shared_mode_diagnostics: dict[str, Any] | None = None,
    workspace_urls: dict[str, str] | None = None,
    expected_workspace_urls: dict[str, str] | None = None,
    manifest_server_urls: dict[str, str] | None = None,
    manifest_health_urls: dict[str, str] | None = None,
    services: dict[str, Any] | None = None,
    docker_available: bool = True,
    inventory_error: str | None = None,
    recovery_classification: str | None = None,
    completed_tool_call_boundary: bool = False,
    last_runtime_action: str | None = None,
    activity_lease_present: bool | None = None,
    execution_lease_present: bool | None = None,
) -> Any:
    readiness = SimpleNamespace(
        ready=ready,
        status=SimpleNamespace(value=readiness_status),
        recommended_action=SimpleNamespace(value=recommended_action),
        issues=tuple(issues),
        reason_codes=tuple(reason_codes),
    )
    recovery = None
    if (
        recovery_classification is not None
        or completed_tool_call_boundary
        or last_runtime_action is not None
    ):
        recovery = SimpleNamespace(
            classification=SimpleNamespace(
                value=recovery_classification or "resume-safe"
            ),
            completed_tool_call_boundary=completed_tool_call_boundary,
            last_trigger=(
                SimpleNamespace(value=last_runtime_action)
                if last_runtime_action is not None
                else None
            ),
        )
    selection = None
    if activity_lease_present is not None or execution_lease_present is not None:
        selection = SimpleNamespace(
            activity_lease=(
                SimpleNamespace(present=bool(activity_lease_present))
                if activity_lease_present is not None
                else None
            ),
            execution_lease=(
                SimpleNamespace(present=bool(execution_lease_present))
                if execution_lease_present is not None
                else None
            ),
        )
    return SimpleNamespace(
        readiness=readiness,
        persisted_runtime_state=persisted_runtime_state,
        docker_available=docker_available,
        inventory_error=inventory_error,
        lifecycle_state=lifecycle_state or factory_stack.RuntimeLifecycleState.RUNNING,
        compose_project_name=compose_project_name,
        shared_mode_diagnostics=shared_mode_diagnostics or {},
        workspace_urls=workspace_urls or {},
        expected_workspace_urls=expected_workspace_urls or {},
        manifest_server_urls=manifest_server_urls or {},
        manifest_health_urls=manifest_health_urls or {},
        services=services or {},
        recovery=recovery,
        selection=selection,
    )


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    git("init", cwd=path)
    git("checkout", "-b", "main", cwd=path)
    git("config", "user.name", "Test User", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)


def refresh_source_release_manifest(path: Path) -> None:
    factory_release.write_release_manifest_file(
        path,
        repo_url=str(path),
        source_ref="main",
    )
    git("add", str(factory_release.RELEASE_MANIFEST_RELATIVE_PATH), cwd=path)
    git("commit", "-m", "Refresh release manifest", cwd=path)


def create_source_factory_repo(path: Path) -> None:
    init_git_repo(path)
    (path / "scripts").mkdir(parents=True, exist_ok=True)
    (path / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (path / "configs").mkdir(parents=True, exist_ok=True)
    (path / "factory_runtime" / "mcp_runtime").mkdir(parents=True, exist_ok=True)
    (path / "manifests").mkdir(parents=True, exist_ok=True)
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
    (path / "scripts" / "factory_release.py").write_text(
        FACTORY_RELEASE_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "factory_update.py").write_text(
        FACTORY_UPDATE_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "verify_factory_install.py").write_text(
        VERIFY_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "factory_stack.py").write_text(
        FACTORY_STACK_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (path / "scripts" / "factory_workspace.py").write_text(
        FACTORY_WORKSPACE_SCRIPT.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for runtime_file in ("__init__.py", "catalog.py", "manager.py", "models.py"):
        (path / "factory_runtime" / "mcp_runtime" / runtime_file).write_text(
            (REPO_ROOT / "factory_runtime" / "mcp_runtime" / runtime_file).read_text(
                encoding="utf-8"
            ),
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
    (path / "factory_runtime" / "secret_safety.py").write_text(
        (REPO_ROOT / "factory_runtime" / "secret_safety.py").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (path / "VERSION").write_text(RELEASE_VERSION + "\n", encoding="utf-8")
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
    refresh_source_release_manifest(path)


def create_release_policy_repo(path: Path, *, version: str = "2.2") -> None:
    init_git_repo(path)
    (path / ".github" / "releases").mkdir(parents=True, exist_ok=True)
    (path / "manifests").mkdir(parents=True, exist_ok=True)
    (path / "VERSION").write_text(f"{version}\n", encoding="utf-8")
    (path / "CHANGELOG.md").write_text(
        "# Changelog\n\n" f"## [{version}] — 2026-04-10\n\n" f"Release {version}.\n",
        encoding="utf-8",
    )
    (path / ".github" / "releases" / f"v{version}.md").write_text(
        f"# Release {version}\n",
        encoding="utf-8",
    )
    factory_release.write_release_manifest_file(
        path,
        repo_url="https://github.com/blecx/softwareFactoryVscode.git",
        source_ref="main",
    )
    git("add", ".", cwd=path)
    git("commit", "-m", f"Seed release {version}", cwd=path)


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
    assert (target_repo / ".copilot/softwareFactoryVscode/.tmp").exists()
    for subdir in factory_workspace.MANAGED_TMP_SUBDIRS:
        assert (target_repo / ".copilot/softwareFactoryVscode/.tmp" / subdir).is_dir()

    factory_env = (
        target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    ).read_text(encoding="utf-8")
    assert f"TARGET_WORKSPACE_PATH={target_repo}" in factory_env
    assert (
        f"FACTORY_DIR={target_repo / '.copilot/softwareFactoryVscode'}" in factory_env
    )
    assert "FACTORY_INSTANCE_ID=factory_" not in factory_env
    assert "FACTORY_INSTANCE_ID=factory-" in factory_env
    assert "CONTEXT7_API_KEY=" in factory_env

    runtime_manifest = json.loads(
        (
            target_repo
            / ".copilot/softwareFactoryVscode/.tmp"
            / "runtime-manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert runtime_manifest["factory_version"] == RELEASE_VERSION
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
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock_data["version"] == RELEASE_VERSION
    assert lock_data["release"]["version_core"] == RELEASE_VERSION
    assert lock_data["release"]["display_version"].startswith(f"{RELEASE_VERSION}+")
    assert lock_data["release"]["commit_sha"] == lock_data["factory"]["commit"]
    assert lock_data["factory"]["repo_url"] == str(source_repo)
    assert lock_data["factory"]["workspace_file"] == "software-factory.code-workspace"
    assert lock_data["factory"]["commit"]

    gitignore = (target_repo / ".gitignore").read_text(encoding="utf-8")
    assert ".copilot/softwareFactoryVscode/.tmp/" in gitignore
    assert ".copilot/softwareFactoryVscode/.factory.env" in gitignore
    assert not (target_repo / ".softwareFactoryVscode").exists()
    assert not (target_repo / ".tmp" / "softwareFactoryVscode").exists()
    assert not (target_repo / ".factory.env").exists()
    assert not (target_repo / ".factory.lock.json").exists()


def test_resolve_version_label_prefers_release_file_for_head_ref(
    tmp_path: Path,
) -> None:
    factory_dir = tmp_path / "factory"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / "VERSION").write_text("2.2\n", encoding="utf-8")

    assert install_factory.resolve_version_label(factory_dir, ref="HEAD") == "2.2"
    assert install_factory.resolve_version_label(factory_dir, ref="") == "2.2"


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
        "Bootstrapping target repository for namespace-first workspace usage"
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
    assert (target_repo / ".copilot/softwareFactoryVscode/.tmp").is_dir()
    assert (
        target_repo / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
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
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert lock_data["release"]["display_version"].startswith(f"{RELEASE_VERSION}+")
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
            target_repo
            / ".copilot/softwareFactoryVscode/.tmp"
            / "runtime-manifest.json"
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
    assert "canonical workspace entrypoint look correct" in verify_result.stdout
    assert "Non-mutating VS Code smoke prompt" not in verify_result.stdout


def test_verify_release_docs_skips_when_version_is_unchanged(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "release-policy-repo"
    create_release_policy_repo(repo)
    (repo / "README.md").write_text("docs only change\n", encoding="utf-8")
    git("add", "README.md", cwd=repo)
    git("commit", "-m", "Docs only", cwd=repo)

    exit_code = verify_release_docs.main(
        ["--repo-root", str(repo), "--base-rev", "HEAD^", "--head-rev", "HEAD"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "VERSION is unchanged" in output


def test_verify_release_docs_requires_changelog_release_notes_and_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "release-policy-repo"
    create_release_policy_repo(repo)
    (repo / "VERSION").write_text("2.3\n", encoding="utf-8")
    git("add", "VERSION", cwd=repo)
    git("commit", "-m", "Bump version only", cwd=repo)

    exit_code = verify_release_docs.main(
        ["--repo-root", str(repo), "--base-rev", "HEAD^", "--head-rev", "HEAD"]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "CHANGELOG.md" in output
    assert ".github/releases/v2.3.md" in output
    assert "manifests/release-manifest.json" in output


def test_verify_release_docs_passes_for_complete_release_bump(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "release-policy-repo"
    create_release_policy_repo(repo)
    (repo / "VERSION").write_text("2.3\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "No unreleased changes.\n\n"
        "## [2.3] — 2026-04-10\n\n"
        "Release 2.3.\n",
        encoding="utf-8",
    )
    (repo / ".github" / "releases" / "v2.3.md").write_text(
        "# Software Factory for VS Code 2.3\n\n"
        "Release 2.3 notes.\n\n"
        "## Delivery status snapshot\n\n"
        "| Scope | Status | Why it matters |\n"
        "| --- | --- | --- |\n"
        "| Per-workspace runtime baseline | Fulfilled for this release | Stable baseline ships now. |\n"
        "| Shared multi-tenant promotion | Open | Safe optimization work stays gated. |\n"
        "| Whole implementation roadmap | Open | The release does not overclaim final completion. |\n",
        encoding="utf-8",
    )
    factory_release.write_release_manifest_file(
        repo,
        repo_url="https://github.com/blecx/softwareFactoryVscode.git",
        source_ref="main",
    )
    git("add", ".", cwd=repo)
    git("commit", "-m", "Prepare release 2.3", cwd=repo)

    exit_code = verify_release_docs.main(
        ["--repo-root", str(repo), "--base-rev", "HEAD^", "--head-rev", "HEAD"]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "includes changelog, release notes, and refreshed release metadata" in output


def test_verify_release_docs_requires_delivery_status_snapshot(
    tmp_path: Path,
    capsys,
) -> None:
    repo = tmp_path / "release-policy-repo"
    create_release_policy_repo(repo)
    (repo / "VERSION").write_text("2.3\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "No unreleased changes.\n\n"
        "## [2.3] — 2026-04-10\n\n"
        "Release 2.3.\n",
        encoding="utf-8",
    )
    (repo / ".github" / "releases" / "v2.3.md").write_text(
        "# Software Factory for VS Code 2.3\n\nRelease 2.3 notes only.\n",
        encoding="utf-8",
    )
    factory_release.write_release_manifest_file(
        repo,
        repo_url="https://github.com/blecx/softwareFactoryVscode.git",
        source_ref="main",
    )
    git("add", ".", cwd=repo)
    git("commit", "-m", "Prepare incomplete release 2.3", cwd=repo)

    exit_code = verify_release_docs.main(
        ["--repo-root", str(repo), "--base-rev", "HEAD^", "--head-rev", "HEAD"]
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Delivery status snapshot" in output
    assert "| Scope | Status | Why it matters |" in output


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
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        custom_env, encoding="utf-8"
    )
    tmp_dir = target_repo / ".copilot/softwareFactoryVscode/.tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    (tmp_dir / "foo.txt").write_text("running")

    assert (
        install_factory.main(
            [
                "--target",
                str(target_repo),
                "--repo-url",
                str(source_repo),
                "--update",
                "--force-workspace",
            ]
        )
        == 0
    )

    # Workspace overwritten (force-workspace passed)
    assert '"custom": true' not in workspace_path.read_text(encoding="utf-8")

    # env preserved
    updated_env = (
        target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    ).read_text(encoding="utf-8")
    assert "CONTEXT7_API_KEY=abc123" in updated_env
    assert "PORT_BASH=" in updated_env

    # tmp untouched
    assert (tmp_dir / "foo.txt").exists()


def test_update_ignores_local_backup_branch_and_resets_to_latest_source(
    tmp_path: Path,
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

    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / "DIRTY_NOTE.txt").write_text("keep me in backup\n", encoding="utf-8")

    (source_repo / "NEW_UPDATE_MARKER.txt").write_text(
        "latest commit payload\n",
        encoding="utf-8",
    )
    git("add", "NEW_UPDATE_MARKER.txt", cwd=source_repo)
    git("commit", "-m", "Advance factory source", cwd=source_repo)
    refresh_source_release_manifest(source_repo)
    latest_source_head = git("rev-parse", "HEAD", cwd=source_repo).stdout.strip()

    assert (
        install_factory.main(
            [
                "--target",
                str(target_repo),
                "--repo-url",
                str(source_repo),
                "--update",
            ]
        )
        == 0
    )

    target_head = git("rev-parse", "HEAD", cwd=factory_dir).stdout.strip()
    target_branch = git("branch", "--show-current", cwd=factory_dir).stdout.strip()
    backup_branches = git("branch", "--list", "local-backup-*", cwd=factory_dir).stdout
    lock_data = json.loads((factory_dir / "lock.json").read_text(encoding="utf-8"))

    assert target_head == latest_source_head
    assert target_branch == "main"
    assert "local-backup-" in backup_branches
    assert lock_data["version"] == RELEASE_VERSION
    assert lock_data["factory"]["commit"] == latest_source_head
    assert (factory_dir / "NEW_UPDATE_MARKER.txt").exists()
    assert not (factory_dir / "DIRTY_NOTE.txt").exists()


def test_factory_update_check_reports_when_source_manifest_is_newer(
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

    (source_repo / "UPDATE_PAYLOAD.txt").write_text(
        "new manifest payload\n", encoding="utf-8"
    )
    git("add", "UPDATE_PAYLOAD.txt", cwd=source_repo)
    git("commit", "-m", "Advance source repo for updater", cwd=source_repo)
    refresh_source_release_manifest(source_repo)

    exit_code = factory_update.main(
        ["check", "--target", str(target_repo), "--repo-url", str(source_repo)]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "update_status=update-available" in output
    assert "update_available=true" in output


def test_factory_update_apply_refreshes_install_from_source_manifest(
    tmp_path: Path,
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

    (source_repo / "APPLY_UPDATE_MARKER.txt").write_text(
        "updater applied new payload\n", encoding="utf-8"
    )
    git("add", "APPLY_UPDATE_MARKER.txt", cwd=source_repo)
    git("commit", "-m", "Advance source repo for updater apply", cwd=source_repo)
    refresh_source_release_manifest(source_repo)
    latest_source_head = git("rev-parse", "HEAD", cwd=source_repo).stdout.strip()

    exit_code = factory_update.main(
        ["apply", "--target", str(target_repo), "--repo-url", str(source_repo)]
    )
    lock_data = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )

    assert exit_code == 0
    assert lock_data["factory"]["commit"] == latest_source_head
    assert (
        target_repo / ".copilot/softwareFactoryVscode" / "APPLY_UPDATE_MARKER.txt"
    ).exists()


def test_factory_update_check_uses_live_local_source_head_when_manifest_lags(
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

    initial_manifest = json.loads(
        (source_repo / "manifests/release-manifest.json").read_text(encoding="utf-8")
    )
    initial_manifest_commit = initial_manifest["latest"]["commit_sha"]

    (source_repo / "LOCAL_HEAD_ONLY_UPDATE.txt").write_text(
        "live local source head\n", encoding="utf-8"
    )
    git("add", "LOCAL_HEAD_ONLY_UPDATE.txt", cwd=source_repo)
    git(
        "commit",
        "-m",
        "Advance source repo without refreshing manifest",
        cwd=source_repo,
    )
    latest_source_head = git("rev-parse", "HEAD", cwd=source_repo).stdout.strip()

    stale_manifest = json.loads(
        (source_repo / "manifests/release-manifest.json").read_text(encoding="utf-8")
    )
    assert stale_manifest["latest"]["commit_sha"] == initial_manifest_commit
    assert stale_manifest["latest"]["commit_sha"] != latest_source_head

    assert (
        factory_update.main(
            ["check", "--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )
    check_output = capsys.readouterr().out
    assert "update_status=update-available" in check_output
    assert "latest_commit=" + latest_source_head in check_output

    assert (
        factory_update.main(
            ["apply", "--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        factory_update.main(
            ["check", "--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )
    final_output = capsys.readouterr().out
    assert "update_status=up-to-date" in final_output
    assert "update_available=false" in final_output
    assert "installed_commit=" + latest_source_head in final_output
    assert "latest_commit=" + latest_source_head in final_output


def test_release_update_smoke_flow(tmp_path: Path, capsys) -> None:
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

    initial_lock = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert initial_lock["release"]["display_version"].startswith(f"{RELEASE_VERSION}+")

    (source_repo / "SMOKE_UPDATE_MARKER.txt").write_text(
        "smoke update payload\n", encoding="utf-8"
    )
    git("add", "SMOKE_UPDATE_MARKER.txt", cwd=source_repo)
    git("commit", "-m", "Advance source repo for smoke test", cwd=source_repo)
    refresh_source_release_manifest(source_repo)

    assert (
        factory_update.main(
            ["check", "--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )
    check_output = capsys.readouterr().out
    assert "update_status=update-available" in check_output

    assert (
        factory_update.main(
            ["apply", "--target", str(target_repo), "--repo-url", str(source_repo)]
        )
        == 0
    )

    updated_lock = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )
    updated_manifest = json.loads(
        (
            target_repo
            / ".copilot/softwareFactoryVscode/.tmp"
            / "runtime-manifest.json"
        ).read_text(encoding="utf-8")
    )
    latest_source_head = git("rev-parse", "HEAD", cwd=source_repo).stdout.strip()

    assert updated_lock["factory"]["commit"] == latest_source_head
    assert updated_lock["release"]["commit_sha"] == latest_source_head
    assert updated_manifest["factory_release"]["commit_sha"] == latest_source_head
    assert (
        target_repo / ".copilot/softwareFactoryVscode" / "SMOKE_UPDATE_MARKER.txt"
    ).exists()

    assert (
        verify_factory_install.main(["--target", str(target_repo), "--no-smoke-prompt"])
        == 0
    )


def test_update_removes_legacy_factory_gitignore_block(tmp_path: Path) -> None:
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

    (target_repo / ".gitignore").write_text(
        "\n".join(
            [
                "# Hidden-tree softwareFactoryVscode install artifacts",
                ".softwareFactoryVscode/",
                ".factory.env",
                ".factory.lock.json",
                ".tmp/",
                "# Factory Isolation",
                ".copilot/softwareFactoryVscode/.tmp/",
                ".copilot/softwareFactoryVscode/.factory.env",
                "",
            ]
        ),
        encoding="utf-8",
    )

    assert (
        install_factory.main(
            [
                "--target",
                str(target_repo),
                "--repo-url",
                str(source_repo),
                "--update",
            ]
        )
        == 0
    )

    gitignore = (target_repo / ".gitignore").read_text(encoding="utf-8")
    assert "# Hidden-tree softwareFactoryVscode install artifacts" not in gitignore
    assert ".softwareFactoryVscode/" not in gitignore
    assert ".factory.lock.json" not in gitignore
    assert ".copilot/softwareFactoryVscode/.tmp/" in gitignore
    assert ".copilot/softwareFactoryVscode/.factory.env" in gitignore


def test_update_refresh_preserves_active_workspace_and_runtime_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda _repo_root, _command: None,
    )

    source_repo = tmp_path / "source-factory"
    target_repo = tmp_path / "target-project"
    create_source_factory_repo(source_repo)
    init_git_repo(target_repo)

    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    git("clone", str(source_repo), str(factory_dir), cwd=target_repo)
    subprocess.run(["bash", "setup.sh"], cwd=factory_dir, check=True, text=True)

    assert (
        bootstrap_host.main(
            [
                "--target",
                str(target_repo),
                "--repo-url",
                str(source_repo),
            ]
        )
        == 0
    )

    config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=True,
    )

    (source_repo / "RUNTIME_STATE_UPDATE_MARKER.txt").write_text(
        "advance source for state-preserving update\n",
        encoding="utf-8",
    )
    git("add", "RUNTIME_STATE_UPDATE_MARKER.txt", cwd=source_repo)
    git(
        "commit",
        "-m",
        "Advance source for state-preserving update",
        cwd=source_repo,
    )
    refresh_source_release_manifest(source_repo)

    real_subprocess_run = install_factory.subprocess.run
    intercepted_stop_commands: list[list[str]] = []

    def _patched_subprocess_run(command, *args, **kwargs):
        command_parts = [str(part) for part in command]
        if (
            len(command_parts) >= 5
            and command_parts[1].endswith("factory_stack.py")
            and command_parts[2] == "stop"
        ):
            intercepted_stop_commands.append(command_parts)
            repo_root_value = command_parts[command_parts.index("--repo-root") + 1]
            factory_stack.stop_stack(
                Path(repo_root_value),
                preserve_runtime_state="--preserve-runtime-state" in command_parts,
            )
            return subprocess.CompletedProcess(command_parts, 0, "", "")

        return real_subprocess_run(command, *args, **kwargs)

    monkeypatch.setattr(install_factory.subprocess, "run", _patched_subprocess_run)

    assert (
        install_factory.main(
            [
                "--target",
                str(target_repo),
                "--repo-url",
                str(source_repo),
                "--update",
            ]
        )
        == 0
    )

    assert intercepted_stop_commands
    assert "--preserve-runtime-state" in intercepted_stop_commands[0]

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )


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


def test_bootstrap_without_explicit_metadata_preserves_existing_lock_values(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (target_repo / ".copilot/softwareFactoryVscode/lock.json").write_text(
        json.dumps(
            {
                "version": "2.2",
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

    exit_code = bootstrap_host.main(
        [
            "--target",
            str(target_repo),
        ]
    )

    lock_data = json.loads(
        (target_repo / ".copilot/softwareFactoryVscode/lock.json").read_text(
            encoding="utf-8"
        )
    )
    assert exit_code == 0
    assert lock_data["version"] == "2.2"
    assert lock_data["factory"]["repo_url"] == "https://example.invalid/factory.git"
    assert lock_data["factory"]["commit"] == "deadbeef"


def test_bootstrap_runtime_sync_preserves_active_workspace_and_runtime_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=True,
    )

    bootstrap_host.sync_factory_runtime_contract(
        target_repo,
        workspace_file="software-factory.code-workspace",
    )

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )


def test_bootstrap_refreshes_generated_workspace_without_force(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    runtime_config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    stale_workspace = {
        "folders": [
            {"name": "Host Project (Root)", "path": "."},
            {
                "name": "AI Agent Factory",
                "path": ".copilot/softwareFactoryVscode",
            },
        ],
        "settings": {
            "chat.agent.maxRequests": 50,
            "workbench.colorTheme": "Ayu Dark",
            "mcp": {
                "servers": {
                    "context7": {"url": "http://127.0.0.1:3510/mcp"},
                    "bashGateway": {"url": "http://127.0.0.1:3511/mcp"},
                }
            },
        },
    }
    workspace_path = target_repo / "software-factory.code-workspace"
    workspace_path.write_text(
        json.dumps(stale_workspace, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    _, status = bootstrap_host.ensure_workspace_file(
        target_repo,
        "software-factory.code-workspace",
        runtime_config,
        force=False,
    )

    refreshed = json.loads(workspace_path.read_text(encoding="utf-8"))
    assert status == "updated"
    assert refreshed["settings"]["workbench.colorTheme"] == "Ayu Dark"
    assert (
        refreshed["settings"]["mcp"]["servers"]["context7"]["url"]
        == f"http://127.0.0.1:{runtime_config.ports['PORT_CONTEXT7']}/mcp"
    )
    assert (
        refreshed["settings"]["mcp"]["servers"]["bashGateway"]["url"]
        == f"http://127.0.0.1:{runtime_config.ports['PORT_BASH']}/mcp"
    )


def test_factory_orchestrator_loads_workspace_id_from_companion_runtime_manifest(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "host"
    source_repo = target_repo / "work" / "softwareFactoryVscode"
    manifest_path = (
        target_repo / ".copilot/softwareFactoryVscode/.tmp/runtime-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"project_workspace_id": "host-workspace"}, indent=2) + "\n",
        encoding="utf-8",
    )
    source_repo.mkdir(parents=True, exist_ok=True)

    assert factory_agents._load_workspace_id(source_repo) == "host-workspace"


def test_factory_orchestrator_store_lesson_uses_memory_tool_contract(
    tmp_path: Path,
) -> None:
    orchestrator = factory_agents.FactoryOrchestrator(
        server_urls={},
        workspace_root=tmp_path,
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    class FakeMCP:
        async def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
            calls.append((name, args))
            return {"ok": True}

    decision = SimpleNamespace(complexity_score=7, coder_model_tier="full")
    coder_result = SimpleNamespace(
        files_changed=["src/example.py"],
        tests_passed=True,
    )

    asyncio.run(
        orchestrator._store_lesson(
            mcp=FakeMCP(),
            issue_number=42,
            repo="blecx/softwareFactoryVscode",
            decision=decision,
            coder_result=coder_result,
            pr_url="https://example.invalid/pr/42",
        )
    )

    assert len(calls) == 1
    tool_name, payload = calls[0]
    assert tool_name == "memory_store_lesson"
    assert payload["issue_number"] == 42
    assert payload["repo"] == "blecx/softwareFactoryVscode"
    assert payload["outcome"] == "success"
    assert payload["summary"].startswith("Issue #42 in blecx/softwareFactoryVscode")
    assert isinstance(payload["learnings"], list)
    assert any(item == "Model tier used: full" for item in payload["learnings"])
    assert "tags" not in payload
    assert "insight" not in payload


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


def test_verify_factory_install_fails_when_legacy_gitignore_entries_remain(
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
        "factory_release.py",
        "factory_update.py",
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
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    runtime_config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        runtime_config,
        runtime_state="installed",
        active=False,
    )
    (target_repo / ".gitignore").write_text(
        "\n".join(
            [
                "# Hidden-tree softwareFactoryVscode install artifacts",
                ".softwareFactoryVscode/",
                ".factory.env",
                ".factory.lock.json",
                ".tmp/",
                "# Factory Isolation",
                ".copilot/softwareFactoryVscode/.tmp/",
                ".copilot/softwareFactoryVscode/.factory.env",
                "",
            ]
        ),
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": runtime_config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo)])

    assert exit_code == 1


def test_verify_factory_install_flags_partial_legacy_gitignore_entries(
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
        "factory_release.py",
        "factory_update.py",
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
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    runtime_config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        runtime_config,
        runtime_state="installed",
        active=False,
    )
    (target_repo / ".gitignore").write_text(
        "\n".join(
            [
                ".factory.env",
                ".tmp/",
                "# Factory Isolation",
                ".copilot/softwareFactoryVscode/.tmp/",
                ".copilot/softwareFactoryVscode/.factory.env",
                "",
            ]
        ),
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": runtime_config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo)])

    assert exit_code == 1


def test_verify_factory_install_fails_when_workspace_file_missing(
    tmp_path: Path,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode").mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode" / ".git").mkdir(
        parents=True, exist_ok=True
    )
    (target_repo / ".copilot/softwareFactoryVscode" / "scripts").mkdir(
        parents=True, exist_ok=True
    )
    for script_name in (
        "factory_release.py",
        "factory_update.py",
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (
            target_repo / ".copilot/softwareFactoryVscode" / "scripts" / script_name
        ).write_text("# stub\n", encoding="utf-8")
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
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
        "factory_release.py",
        "factory_update.py",
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
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
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
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "factory_release.py",
        "factory_update.py",
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
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
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    runtime_config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        runtime_config,
        runtime_state="running",
        active=False,
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": runtime_config.workspace_settings,
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
        verify_factory_install.factory_stack.shutil,
        "which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        verify_factory_install,
        "collect_running_services",
        lambda compose_name: services,
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(runtime_config),
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        verify_factory_install.factory_stack,
        registry_path=registry_path,
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
    assert "X-Workspace-ID" in prompt
    assert "expected tenant identity" in prompt
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
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "factory_release.py",
        "factory_update.py",
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
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
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


def test_verify_factory_runtime_reports_needs_ramp_up_after_stop(
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
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".git").mkdir(parents=True, exist_ok=True)
    (factory_dir / "scripts").mkdir(parents=True, exist_ok=True)
    for script_name in (
        "factory_release.py",
        "factory_update.py",
        "install_factory.py",
        "bootstrap_host.py",
        "verify_factory_install.py",
    ):
        (factory_dir / "scripts" / script_name).write_text("# stub\n", encoding="utf-8")
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (factory_dir / "configs").mkdir(parents=True, exist_ok=True)
    (factory_dir / "configs" / "bash_gateway_policy.default.yml").write_text(
        (REPO_ROOT / "configs" / "bash_gateway_policy.default.yml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"PROJECT_WORKSPACE_ID={target_repo.name}",
                f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
        encoding="utf-8",
    )
    runtime_config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    factory_workspace.sync_runtime_artifacts(
        runtime_config,
        runtime_state="running",
        active=False,
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": runtime_config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack.shutil,
        "which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda _repo_root, _command: None,
    )
    factory_stack.stop_stack(factory_dir, env_file=env_path, remove_volumes=True)
    capsys.readouterr()

    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "collect_running_services",
        lambda _compose_name: (_ for _ in ()).throw(
            AssertionError(
                "runtime verification should stop at manager-backed preflight when "
                "the runtime is explicitly stopped"
            )
        ),
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "start",
            "reason_codes": ["no-running-services"],
            "issues": [],
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.STOPPED,
                persisted_runtime_state="stopped",
                readiness_status="needs-ramp-up",
                recommended_action="start",
                ready=False,
            ),
        },
    )

    exit_code = verify_factory_install.main(["--target", str(target_repo), "--runtime"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Runtime compliance failed" in output
    assert "needs-ramp-up" in output
    assert "recommended_action=`start`" in output


def test_factory_stack_builds_full_compose_command(tmp_path: Path) -> None:
    repo_root = tmp_path / ".copilot/softwareFactoryVscode"
    repo_root.mkdir(parents=True, exist_ok=True)
    env_file = repo_root / ".factory.env"

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


def test_sync_runtime_artifacts_precreates_instance_data_dirs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "throwaway-target"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
    )

    data_root = factory_dir / "data"
    assert (data_root / "memory" / config.factory_instance_id).is_dir()
    assert (data_root / "bus" / config.factory_instance_id).is_dir()


def test_sync_runtime_artifacts_creates_workspace_file_when_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "throwaway-target"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (factory_dir / "workspace.code-workspace.template").write_text(
        WORKSPACE_TEMPLATE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
    )

    workspace_path = target_repo / "software-factory.code-workspace"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))

    assert workspace["folders"][:2] == [
        {"name": "Host Project (Root)", "path": "."},
        {"name": "AI Agent Factory", "path": ".copilot/softwareFactoryVscode"},
    ]
    assert (
        workspace["settings"]["mcp"]["servers"]["context7"]["url"]
        == f"http://127.0.0.1:{config.ports['PORT_CONTEXT7']}/mcp"
    )


def test_factory_stack_start_from_source_checkout_writes_companion_workspace_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

    target_repo = tmp_path / "host"
    source_repo = target_repo / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True)
    (source_repo / ".copilot" / "config").mkdir(parents=True)
    (source_repo / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (source_repo / "workspace.code-workspace.template").write_text(
        WORKSPACE_TEMPLATE.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    companion_env = target_repo / ".copilot" / "softwareFactoryVscode" / ".factory.env"
    companion_env.parent.mkdir(parents=True, exist_ok=True)
    companion_env.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=host",
                "COMPOSE_PROJECT_NAME=factory_host",
                f"FACTORY_DIR={source_repo}",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda repo, command: None,
    )
    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda compose_project_name: {},
    )

    factory_stack.start_stack(source_repo, build=False, wait=False)

    workspace_path = target_repo / "software-factory.code-workspace"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))

    assert (
        workspace["settings"]["mcp"]["servers"]["context7"]["url"]
        == "http://127.0.0.1:3010/mcp"
    )
    registry = factory_workspace.load_registry(registry_path)
    workspace_records = registry.get("workspaces", {})
    assert any(
        record.get("target_workspace_path") == str(target_repo)
        for record in workspace_records.values()
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
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
        build=False,
        wait=False,
    )
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )
    assert registry["active_workspace"] == ""

    factory_stack.activate_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )

    factory_stack.stop_stack(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "stopped"
    )
    assert registry["active_workspace"] == config.factory_instance_id

    factory_stack.deactivate_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == ""
    assert len(calls) == 2


def test_activate_workspace_refreshes_generated_runtime_artifacts(
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
        config,
        runtime_state="installed",
        active=False,
    )

    workspace_path = target_repo / "software-factory.code-workspace"
    stale_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    stale_workspace["settings"]["mcp"]["servers"]["context7"][
        "url"
    ] = "http://127.0.0.1:3510/mcp"
    workspace_path.write_text(
        json.dumps(stale_workspace, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    stale_manifest = json.loads(
        config.runtime_manifest_path.read_text(encoding="utf-8")
    )
    stale_manifest["mcp_servers"]["context7"]["url"] = "http://127.0.0.1:3510/mcp"
    config.runtime_manifest_path.write_text(
        json.dumps(stale_manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    factory_stack.activate_workspace(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    refreshed_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    refreshed_manifest = json.loads(
        config.runtime_manifest_path.read_text(encoding="utf-8")
    )
    expected_context7_url = f"http://127.0.0.1:{config.ports['PORT_CONTEXT7']}/mcp"

    assert (
        refreshed_workspace["settings"]["mcp"]["servers"]["context7"]["url"]
        == expected_context7_url
    )
    assert refreshed_manifest["mcp_servers"]["context7"]["url"] == expected_context7_url

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id


def test_activate_workspace_is_idempotent_when_runtime_metadata_is_unchanged(
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
        config,
        runtime_state="installed",
        active=False,
    )

    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    workspace_path = target_repo / "software-factory.code-workspace"

    factory_stack.activate_workspace(repo_root, env_file=env_path)
    first_workspace = workspace_path.read_text(encoding="utf-8")
    first_env = env_path.read_text(encoding="utf-8")
    first_manifest = json.loads(
        config.runtime_manifest_path.read_text(encoding="utf-8")
    )

    factory_stack.activate_workspace(repo_root, env_file=env_path)
    second_workspace = workspace_path.read_text(encoding="utf-8")
    second_env = env_path.read_text(encoding="utf-8")
    second_manifest = json.loads(
        config.runtime_manifest_path.read_text(encoding="utf-8")
    )

    assert second_workspace == first_workspace
    assert second_env == first_env
    assert second_manifest["mcp_servers"] == first_manifest["mcp_servers"]

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config.factory_instance_id


def test_activate_workspace_recovers_effective_ports_from_runtime_metadata_when_env_drifted(
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

    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    non_default_env = "\n".join(
        [
            f"TARGET_WORKSPACE_PATH={target_repo}",
            "PROJECT_WORKSPACE_ID=target-project",
            "COMPOSE_PROJECT_NAME=factory_target-project",
            f"FACTORY_DIR={repo_root}",
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
    env_path.write_text(non_default_env, encoding="utf-8")

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
    )

    stale_default_ports = factory_workspace.build_port_values(0)
    drifted_env = "\n".join(
        [
            f"TARGET_WORKSPACE_PATH={target_repo}",
            "PROJECT_WORKSPACE_ID=target-project",
            "COMPOSE_PROJECT_NAME=factory_target-project",
            f"FACTORY_DIR={repo_root}",
            f"FACTORY_INSTANCE_ID={config.factory_instance_id}",
            "FACTORY_PORT_INDEX=0",
            *[f"{key}={value}" for key, value in stale_default_ports.items()],
            "CONTEXT7_API_KEY=",
            "",
        ]
    )
    env_path.write_text(drifted_env, encoding="utf-8")

    workspace_path = target_repo / "software-factory.code-workspace"
    stale_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    stale_workspace["settings"]["mcp"]["servers"]["context7"][
        "url"
    ] = "http://127.0.0.1:3010/mcp"
    stale_workspace["settings"]["mcp"]["servers"]["bashGateway"][
        "url"
    ] = "http://127.0.0.1:3011/mcp"
    workspace_path.write_text(
        json.dumps(stale_workspace, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    factory_stack.activate_workspace(repo_root, env_file=env_path)

    refreshed_env = factory_workspace.parse_env_file(env_path)
    refreshed_workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    refreshed_manifest = json.loads(
        config.runtime_manifest_path.read_text(encoding="utf-8")
    )

    assert refreshed_env["FACTORY_PORT_INDEX"] == str(config.port_index)
    assert refreshed_env["PORT_CONTEXT7"] == str(config.ports["PORT_CONTEXT7"])
    assert refreshed_env["PORT_BASH"] == str(config.ports["PORT_BASH"])

    assert (
        refreshed_workspace["settings"]["mcp"]["servers"]["context7"]["url"]
        == config.mcp_server_urls["context7"]
    )
    assert (
        refreshed_workspace["settings"]["mcp"]["servers"]["bashGateway"]["url"]
        == config.mcp_server_urls["bashGateway"]
    )
    assert (
        refreshed_manifest["mcp_servers"]["context7"]["url"]
        == config.mcp_server_urls["context7"]
    )
    assert (
        refreshed_manifest["mcp_servers"]["bashGateway"]["url"]
        == config.mcp_server_urls["bashGateway"]
    )


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
            repo_root,
            env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
            build=False,
            wait=False,
        )
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError("Expected compose failure to bubble up.")

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "failed"
    )


def test_factory_stack_start_proceeds_when_local_port_probe_false_positives(
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
    (repo_root / "workspace.code-workspace.template").write_text(
        WORKSPACE_TEMPLATE.read_text(encoding="utf-8"),
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
        factory_stack,
        "collect_running_services",
        lambda compose_project_name: {},
    )
    monkeypatch.setattr(
        factory_stack.factory_workspace,
        "ports_available",
        lambda ports: False,
    )
    monkeypatch.setattr(
        factory_stack.factory_workspace,
        "can_bind_port",
        lambda port: False,
    )

    factory_stack.start_stack(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
        build=False,
        wait=False,
    )

    assert len(calls) == 1
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
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
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=test-context7-key\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="running", active=False
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
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
    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda compose_project_name: build_full_service_inventory(
            config,
            agent_worker_status="Restarting (1) 3 seconds ago",
        ),
    )

    factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    output = capsys.readouterr().out

    assert "runtime_state=degraded" in output
    assert "preflight_status=degraded" in output
    assert "recommended_action=inspect" in output
    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"]
        == "degraded"
    )


def test_factory_stack_status_demotes_running_workspace_to_stopped_when_services_missing(
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
        config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should not re-infer runtime truth when preflight already provides a snapshot"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "start",
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.STOPPED,
                persisted_runtime_state="running",
                readiness_status="needs-ramp-up",
                recommended_action="start",
                ready=False,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=stopped" in output
    assert "recommended_action=start" in output

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "stopped"
    )


def test_factory_stack_status_surfaces_bounded_suspended_state(
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
        config,
        runtime_state=factory_stack.RuntimeLifecycleState.SUSPENDED.value,
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should not re-infer runtime truth when preflight already provides a snapshot"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "resume",
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.SUSPENDED,
                persisted_runtime_state=factory_stack.RuntimeLifecycleState.SUSPENDED.value,
                readiness_status="needs-ramp-up",
                recommended_action="resume",
                ready=False,
                recovery_classification="resume-safe",
                completed_tool_call_boundary=True,
                last_runtime_action="suspend",
                activity_lease_present=True,
                execution_lease_present=True,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=suspended" in output
    assert "recommended_action=resume" in output
    assert "recovery_classification=resume-safe" in output
    assert "completed_tool_call_boundary=true" in output
    assert "last_runtime_action=suspend" in output
    assert "activity_lease_present=true" in output
    assert "execution_lease_present=true" in output

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"]
        == "suspended"
    )


def test_factory_stack_suspend_workspace_reports_recovery_metadata(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    env_path = tmp_path / ".factory.env"
    env_path.write_text("", encoding="utf-8")
    calls: list[tuple[Path, Path | None, bool]] = []

    snapshot = SimpleNamespace(
        workspace_id="target-project",
        instance_id="factory-target-project",
        lifecycle_state=factory_stack.RuntimeLifecycleState.SUSPENDED,
        recovery=SimpleNamespace(
            classification=SimpleNamespace(value="resume-safe"),
            completed_tool_call_boundary=True,
        ),
    )

    class FakeRuntimeManager:
        def suspend(
            self,
            repo_root: Path,
            *,
            env_file: Path | None = None,
            completed_tool_call_boundary: bool = False,
        ) -> Any:
            calls.append((repo_root, env_file, completed_tool_call_boundary))
            return snapshot

    monkeypatch.setattr(
        factory_stack,
        "build_runtime_manager",
        lambda: FakeRuntimeManager(),
    )

    exit_code = factory_stack.suspend_workspace(
        tmp_path,
        env_file=env_path,
        completed_tool_call_boundary=True,
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [(tmp_path, env_path, True)]
    assert "workspace_id=target-project" in output
    assert "instance_id=factory-target-project" in output
    assert "runtime_state=suspended" in output
    assert "recovery_classification=resume-safe" in output
    assert "completed_tool_call_boundary=true" in output


def test_factory_stack_resume_workspace_reports_readiness_and_recovery(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    env_path = tmp_path / ".factory.env"
    env_path.write_text("", encoding="utf-8")
    calls: list[tuple[Path, Path | None]] = []

    snapshot = SimpleNamespace(
        workspace_id="target-project",
        instance_id="factory-target-project",
        lifecycle_state=factory_stack.RuntimeLifecycleState.RUNNING,
        readiness=SimpleNamespace(
            status=SimpleNamespace(value="ready"),
            recommended_action=SimpleNamespace(value="none"),
        ),
        recovery=SimpleNamespace(
            classification=SimpleNamespace(value="resume-safe"),
            completed_tool_call_boundary=True,
        ),
    )

    class FakeRuntimeManager:
        def resume(
            self,
            repo_root: Path,
            *,
            env_file: Path | None = None,
        ) -> Any:
            calls.append((repo_root, env_file))
            return snapshot

    monkeypatch.setattr(
        factory_stack,
        "build_runtime_manager",
        lambda: FakeRuntimeManager(),
    )

    exit_code = factory_stack.resume_workspace(tmp_path, env_file=env_path)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert calls == [(tmp_path, env_path)]
    assert "workspace_id=target-project" in output
    assert "instance_id=factory-target-project" in output
    assert "runtime_state=running" in output
    assert "preflight_status=ready" in output
    assert "recommended_action=none" in output
    assert "recovery_classification=resume-safe" in output
    assert "completed_tool_call_boundary=true" in output


def test_factory_stack_status_preserves_failed_state_when_services_missing(
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
        config,
        runtime_state="failed",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should not re-infer runtime truth when preflight already provides a snapshot"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "start",
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.STOPPED,
                persisted_runtime_state="failed",
                readiness_status="needs-ramp-up",
                recommended_action="start",
                ready=False,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=failed" in output

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "failed"
    )


def test_factory_stack_status_recovers_missing_registry_record(
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
        config,
        runtime_state="installed",
        active=False,
    )

    registry = factory_workspace.load_registry(registry_path)
    del registry["workspaces"][config.factory_instance_id]
    factory_workspace.save_registry(registry, registry_path)

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should not re-infer runtime truth when preflight already provides a snapshot"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "start",
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.STOPPED,
                persisted_runtime_state="installed",
                readiness_status="needs-ramp-up",
                recommended_action="start",
                ready=False,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "Recovered missing registry record" in output

    updated = factory_workspace.load_registry(registry_path)
    assert config.factory_instance_id in updated.get("workspaces", {})


def test_factory_stack_stop_marks_failed_state_when_compose_down_fails(
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
        config,
        runtime_state="running",
        active=False,
    )

    def _raise_stop_failure(_repo_root: Path, _command: list[str]) -> None:
        raise subprocess.CalledProcessError(1, ["docker", "compose", "down"])

    monkeypatch.setattr(factory_stack, "run_compose_command", _raise_stop_failure)

    with pytest.raises(subprocess.CalledProcessError):
        factory_stack.stop_stack(
            repo_root,
            env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
        )

    output = capsys.readouterr().out
    assert "Runtime state marked as `failed`" in output

    registry = factory_workspace.load_registry(registry_path)
    assert (
        registry["workspaces"][config.factory_instance_id]["runtime_state"] == "failed"
    )


def test_factory_stack_stop_reports_hygiene_semantics(
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
        config,
        runtime_state="running",
        active=False,
    )

    commands: list[list[str]] = []

    def _record_stop(_repo_root: Path, command: list[str]) -> None:
        commands.append(command)

    monkeypatch.setattr(factory_stack, "run_compose_command", _record_stop)

    factory_stack.stop_stack(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    first_output = capsys.readouterr().out

    assert "Removed containers and retained named volumes" in first_output
    assert (
        "retained generated runtime metadata and marked the workspace `stopped`"
        in first_output
    )
    assert "retained Docker images" in first_output
    assert "-v" not in commands[0]

    factory_workspace.update_runtime_state(config.factory_instance_id, "running")
    factory_stack.stop_stack(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
        remove_volumes=True,
        preserve_runtime_state=True,
    )
    second_output = capsys.readouterr().out

    assert "Removed containers and named volumes" in second_output
    assert "preserved existing runtime-state metadata" in second_output
    assert "retained Docker images" in second_output
    assert "-v" in commands[1]


def test_factory_stack_stop_followed_by_status_reports_needs_ramp_up(
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
        config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda _repo_root, _command: None,
    )
    factory_stack.stop_stack(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    capsys.readouterr()

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should rely on the manager-backed preflight "
                "snapshot after an explicit stop"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "recommended_action": "start",
            "reason_codes": ["no-running-services"],
            "issues": [],
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.STOPPED,
                persisted_runtime_state="stopped",
                readiness_status="needs-ramp-up",
                recommended_action="start",
                ready=False,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=stopped" in output
    assert "preflight_status=needs-ramp-up" in output
    assert "recommended_action=start" in output


def test_factory_stack_list_reports_registry_reconciliation_conflicts(
    monkeypatch,
    capsys,
) -> None:
    def _raise_reconciliation_conflict(*_args, **_kwargs):
        raise RuntimeError("simulated registry conflict")

    monkeypatch.setattr(
        factory_stack.factory_workspace,
        "reconcile_registry",
        _raise_reconciliation_conflict,
    )

    exit_code = factory_stack.list_workspaces()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "Registry reconciliation failed" in output
    assert "simulated registry conflict" in output


def test_build_runtime_config_preserves_persisted_ports_when_workspace_reopens(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    initial_config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )
    factory_workspace.sync_runtime_artifacts(
        initial_config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: False)

    reopened_config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )

    assert reopened_config.port_index == initial_config.port_index
    assert reopened_config.ports == initial_config.ports
    assert reopened_config.mcp_server_urls == initial_config.mcp_server_urls


def test_build_runtime_config_matches_repo_fundamentals_port_contract(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo,
        factory_dir=factory_dir,
    )

    assert (
        config.mcp_server_urls["git"]
        == f"http://127.0.0.1:{config.ports['PORT_FS']}/mcp"
    )
    assert (
        config.mcp_server_urls["search"]
        == f"http://127.0.0.1:{config.ports['PORT_GIT']}/mcp"
    )
    assert (
        config.mcp_server_urls["filesystem"]
        == f"http://127.0.0.1:{config.ports['PORT_SEARCH']}/mcp"
    )


def test_factory_stack_preflight_reports_needs_ramp_up_for_installed_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    monkeypatch.setattr(factory_stack, "collect_service_inventory", lambda _name: {})

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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=test-context7-key\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "needs-ramp-up"
    assert report["recommended_action"] == "start"
    assert "needs ramp-up" in report["issues"][0]


def test_runtime_manifest_reports_shared_topology_when_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (factory_dir / ".factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                f"FACTORY_DIR={factory_dir}",
                "FACTORY_SHARED_SERVICE_MODE=shared",
                "FACTORY_TENANCY_MODE=shared",
                "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    manifest = factory_workspace.build_runtime_manifest(config)

    assert manifest["runtime_topology"]["mode"] == "shared"
    assert manifest["runtime_health"]["mcp-memory"]["topology_mode"] == "shared"
    assert manifest["runtime_health"]["mcp-memory"]["workspace_owned"] is False
    assert (
        manifest["runtime_health"]["mcp-memory"]["url"]
        == "http://shared-memory.internal:3030/mcp"
    )
    assert (
        manifest["runtime_health"]["approval-gate"]["url"]
        == "http://shared-approval.internal:8001/health"
    )


def test_factory_stack_preflight_treats_promoted_shared_services_as_external(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
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

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    inventory = build_full_service_inventory(config)
    for service_name in ("mcp-memory", "mcp-agent-bus", "approval-gate"):
        del inventory[service_name]

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: inventory,
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "ready"
    assert report["runtime_topology"]["mode"] == "shared"
    assert report["shared_mode_diagnostics"]["shared_mode_status"] == "shared-ready"
    assert report["shared_mode_diagnostics"]["tenant_identity_required"] is True
    assert (
        report["runtime_topology"]["services"]["mcp-memory"]["workspace_owned"] is False
    )


def test_factory_stack_preflight_flags_missing_shared_tenant_enforcement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                f"FACTORY_DIR={repo_root}",
                "FACTORY_SHARED_SERVICE_MODE=shared",
                "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    inventory = build_full_service_inventory(config)
    for service_name in ("mcp-memory", "mcp-agent-bus", "approval-gate"):
        del inventory[service_name]

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: inventory,
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "config-drift"
    assert report["recommended_action"] == "inspect-shared-topology"
    assert (
        report["shared_mode_diagnostics"]["shared_mode_status"]
        == "shared-topology-without-tenant-enforcement"
    )
    assert any(
        "explicit tenant identity enforcement" in issue for issue in report["issues"]
    )


def test_factory_stack_status_reports_shared_mode_tenant_diagnostics(
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
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    env_path = repo_root / ".factory.env"
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

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda compose_project_name: {
            "mock-llm-gateway": "Up 10 seconds (healthy)",
            "agent-worker": "Up 10 seconds (healthy)",
        },
    )
    inventory = build_full_service_inventory(config)
    for service_name in ("mcp-memory", "mcp-agent-bus", "approval-gate"):
        del inventory[service_name]
    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: inventory,
    )

    exit_code = factory_stack.status_workspace(repo_root, env_file=env_path)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "shared_mode_status=shared-ready" in output
    assert "tenant_identity_required=true" in output
    assert "expected_tenant_identity=target-project" in output
    assert "tenant_identity_header=X-Workspace-ID" in output


def test_factory_stack_preflight_flags_workspace_owned_duplicates_in_shared_mode(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
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

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "config-drift"
    assert report["recommended_action"] == "inspect-shared-topology"
    assert any(
        "Shared-service topology drift detected" in issue for issue in report["issues"]
    )


def test_factory_stack_start_scales_promoted_shared_services_to_zero(
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
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
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

    captured_commands: list[list[str]] = []
    monkeypatch.setattr(
        factory_stack,
        "run_compose_command",
        lambda _repo, command: captured_commands.append(list(command)),
    )
    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda compose_project_name: {},
    )

    factory_stack.start_stack(
        repo_root,
        env_file=env_path,
        build=False,
        wait=False,
    )

    command = captured_commands[0]
    assert "--scale" in command
    assert "mcp-memory=0" in command
    assert "mcp-agent-bus=0" in command
    assert "approval-gate=0" in command


def test_factory_stack_preflight_detects_workspace_port_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=test-context7-key\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    stale_workspace = dict(config.workspace_settings)
    stale_workspace = json.loads(json.dumps(stale_workspace))
    stale_workspace["mcp"]["servers"]["context7"]["url"] = "http://127.0.0.1:3510/mcp"
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": stale_workspace,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "config-drift"
    assert report["recommended_action"] == "re-bootstrap"
    assert report["reason_codes"] == ["workspace-url-drift"]
    assert [code.value for code in report["readiness"].reason_codes] == [
        "workspace-url-drift"
    ]
    assert any(
        "Generated workspace MCP URL drift detected" in issue
        for issue in report["issues"]
    )


def test_factory_stack_preflight_reports_missing_required_secret_from_manager(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack, "get_factory_head_commit", lambda _path: "deadbeef"
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    report = factory_stack.build_preflight_report(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )

    assert report["status"] == "config-drift"
    assert "missing-secret" in report["reason_codes"]
    assert any("CONTEXT7_API_KEY" in issue for issue in report["issues"])


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
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        custom_env, encoding="utf-8"
    )

    factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )

    assert (target_repo / ".copilot/softwareFactoryVscode/.factory.env").read_text(
        encoding="utf-8"
    ) == custom_env


def test_factory_stack_status_uses_manager_snapshot_for_runtime_truth(
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
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack,
        "get_factory_head_commit",
        lambda _path: "deadbeef",
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=test-context7-key\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should derive runtime truth from the manager-backed snapshot"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    exit_code = factory_stack.status_workspace(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=running" in output
    assert "preflight_status=ready" in output


def test_factory_stack_status_keeps_running_truth_when_task_metadata_is_absent(
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
        config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should derive runtime truth from the "
                "manager-backed snapshot even when task metadata is absent"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "reason_codes": [],
            "issues": [],
            "snapshot": build_runtime_snapshot_contract(
                lifecycle_state=factory_stack.RuntimeLifecycleState.RUNNING,
                persisted_runtime_state="running",
                readiness_status="ready",
                recommended_action="none",
                ready=True,
                activity_lease_present=False,
                execution_lease_present=False,
            ),
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_state=running" in output
    assert "activity_lease_present=false" in output
    assert "execution_lease_present=false" in output


def test_factory_stack_status_fails_closed_without_manager_snapshot(
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
    (repo_root / ".factory.env").write_text(
        "CONTEXT7_API_KEY=test-context7-key\n",
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should fail closed before trying a Docker-side fallback"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "issues": [],
        },
    )

    exit_code = factory_stack.status_workspace(
        repo_root,
        env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env",
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "preflight_status=error" in output
    assert "manager-backed snapshot" in output


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
    ) -> tuple[Path, Any]:
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
        repo_a,
        env_file=config_a.target_dir / ".copilot/softwareFactoryVscode/.factory.env",
    )
    factory_stack.deactivate_workspace(
        repo_b,
        env_file=config_b.target_dir / ".copilot/softwareFactoryVscode/.factory.env",
    )

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config_a.factory_instance_id


def test_activate_workspace_switch_back_clears_stale_selection_leases(
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
    ) -> tuple[Path, Any]:
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

    def seed_stale_selection_leases(instance_id: str, holder: str) -> None:
        registry = factory_workspace.load_registry(registry_path)
        registry["workspaces"][instance_id].update(
            {
                "activity_lease_present": True,
                "activity_lease_holder": holder,
                "activity_lease_renewed_at": "2026-04-21T10:00:00Z",
                "activity_lease_expires_at": "2026-04-21T10:05:00Z",
                "execution_lease_present": True,
                "execution_lease_holder": f"{holder}-exec",
                "execution_lease_renewed_at": "2026-04-21T10:00:30Z",
                "execution_lease_expires_at": "2026-04-21T10:05:30Z",
            }
        )
        factory_workspace.save_registry(registry, registry_path)

    lease_keys = (
        "activity_lease_present",
        "activity_lease_holder",
        "activity_lease_renewed_at",
        "activity_lease_expires_at",
        "execution_lease_present",
        "execution_lease_holder",
        "execution_lease_renewed_at",
        "execution_lease_expires_at",
    )

    repo_a, config_a = prepare_workspace(tmp_path / "project-a")
    repo_b, config_b = prepare_workspace(tmp_path / "project-b")
    env_a = config_a.target_dir / ".copilot/softwareFactoryVscode/.factory.env"
    env_b = config_b.target_dir / ".copilot/softwareFactoryVscode/.factory.env"

    seed_stale_selection_leases(config_a.factory_instance_id, "stale-a")
    factory_stack.activate_workspace(repo_a, env_file=env_a)

    seed_stale_selection_leases(config_a.factory_instance_id, "stale-a-return")
    seed_stale_selection_leases(config_b.factory_instance_id, "stale-b")
    factory_stack.activate_workspace(repo_b, env_file=env_b)

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config_b.factory_instance_id
    for instance_id in (config_a.factory_instance_id, config_b.factory_instance_id):
        for key in lease_keys:
            assert key not in registry["workspaces"][instance_id]

    seed_stale_selection_leases(config_a.factory_instance_id, "stale-a-final")
    seed_stale_selection_leases(config_b.factory_instance_id, "stale-b-final")
    factory_stack.activate_workspace(repo_a, env_file=env_a)

    registry = factory_workspace.load_registry(registry_path)
    assert registry["active_workspace"] == config_a.factory_instance_id
    for instance_id in (config_a.factory_instance_id, config_b.factory_instance_id):
        for key in lease_keys:
            assert key not in registry["workspaces"][instance_id]

    workspace_a = json.loads(
        (config_a.target_dir / "software-factory.code-workspace").read_text(
            encoding="utf-8"
        )
    )
    workspace_b = json.loads(
        (config_b.target_dir / "software-factory.code-workspace").read_text(
            encoding="utf-8"
        )
    )
    assert (
        workspace_a["settings"]["mcp"]["servers"]["context7"]["url"]
        == config_a.mcp_server_urls["context7"]
    )
    assert (
        workspace_b["settings"]["mcp"]["servers"]["context7"]["url"]
        == config_b.mcp_server_urls["context7"]
    )
    assert config_a.mcp_server_urls["context7"] != config_b.mcp_server_urls["context7"]


def test_deactivate_workspace_clears_target_selection_leases(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )

    target_repo = tmp_path / "project-a"
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
        config,
        runtime_state="installed",
        active=False,
    )
    env_path = config.target_dir / ".copilot/softwareFactoryVscode/.factory.env"

    factory_stack.activate_workspace(repo_root, env_file=env_path)
    registry = factory_workspace.load_registry(registry_path)
    registry["workspaces"][config.factory_instance_id].update(
        {
            "activity_lease_present": True,
            "activity_lease_holder": "stale-holder",
            "execution_lease_present": True,
            "execution_lease_holder": "stale-exec",
        }
    )
    factory_workspace.save_registry(registry, registry_path)

    factory_stack.deactivate_workspace(repo_root, env_file=env_path)

    registry = factory_workspace.load_registry(registry_path)
    record = registry["workspaces"][config.factory_instance_id]
    assert registry["active_workspace"] == ""
    assert "activity_lease_present" not in record
    assert "activity_lease_holder" not in record
    assert "execution_lease_present" not in record
    assert "execution_lease_holder" not in record
    assert record["last_activated_at"] is not None


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
    ) -> tuple[Path, Any]:
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
        repo_a,
        env_file=config_a.target_dir / ".copilot/softwareFactoryVscode/.factory.env",
        build=False,
        wait=False,
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
        "factory_release.py",
        "factory_update.py",
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
            "CONTEXT7_API_KEY=test-context7-key",
            "",
        ]
    )
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        custom_env, encoding="utf-8"
    )
    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config, runtime_state="running", active=False
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
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
        verify_factory_install.factory_stack.shutil,
        "which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "get_factory_head_commit",
        lambda _path: "deadbeef",
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        verify_factory_install.factory_stack,
        registry_path=registry_path,
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


def test_factory_stack_preflight_surfaces_production_mode_without_mock_gateway(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        factory_stack.factory_workspace, "ports_available", lambda ports: True
    )
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack,
        "get_factory_head_commit",
        lambda _path: "deadbeef",
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    env_path = repo_root / ".factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                f"FACTORY_DIR={repo_root}",
                "FACTORY_RUNTIME_MODE=production",
                "GITHUB_TOKEN=test-github-token",
                "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    report = factory_stack.build_preflight_report(repo_root, env_file=env_path)

    assert report["runtime_mode"] == "production"
    assert report["status"] == "ready"
    assert "mock-llm-gateway" not in report["service_inventory"]
    assert "mock-llm-gateway" not in report["expected_service_ports"]


def test_factory_stack_status_reports_production_mode(
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
    monkeypatch.setattr(factory_stack.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(
        factory_stack,
        "get_factory_head_commit",
        lambda _path: "deadbeef",
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        factory_stack,
        registry_path=registry_path,
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
    env_path = repo_root / ".factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                f"FACTORY_DIR={repo_root}",
                "FACTORY_RUNTIME_MODE=production",
                "GITHUB_TOKEN=test-github-token",
                "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(target_repo, factory_dir=repo_root)
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / "software-factory.code-workspace").write_text(
        json.dumps(
            {
                "folders": [
                    {"name": "Host Project (Root)", "path": "."},
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        factory_stack,
        "collect_running_services",
        lambda _compose_project_name: (_ for _ in ()).throw(
            AssertionError(
                "status_workspace should continue to use the manager-backed snapshot in production mode"
            )
        ),
    )
    monkeypatch.setattr(
        factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )

    exit_code = factory_stack.status_workspace(repo_root, env_file=env_path)
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "runtime_mode=production" in output
    assert "preflight_status=ready" in output


def test_verify_runtime_fails_closed_when_production_mode_lacks_github_token(
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
        "factory_release.py",
        "factory_update.py",
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
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                f"PROJECT_WORKSPACE_ID={target_repo.name}",
                f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
                "FACTORY_RUNTIME_MODE=production",
                "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
                ],
                "settings": config.workspace_settings,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack.shutil,
        "which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        verify_factory_install.factory_stack,
        registry_path=registry_path,
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "verify_runtime should stop at manager-backed production preflight when live config is missing"
            )
        ),
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert violations
    assert violations[0].startswith("Runtime preflight reported `config-drift`")
    assert any("GITHUB_TOKEN" in violation for violation in violations)


def test_verify_runtime_uses_production_profile_when_live_github_token_is_present(
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
        "factory_release.py",
        "factory_update.py",
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
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                f"PROJECT_WORKSPACE_ID={target_repo.name}",
                f"COMPOSE_PROJECT_NAME=factory_{target_repo.name}",
                "FACTORY_RUNTIME_MODE=production",
                "GITHUB_TOKEN=test-github-token",
                "GITHUB_OPS_ALLOWED_REPOS=blecx/softwareFactoryVscode",
                "CONTEXT7_API_KEY=test-context7-key",
                "",
            ]
        ),
        encoding="utf-8",
    )
    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=False,
    )
    (target_repo / ".gitignore").write_text(
        "# Factory Isolation\n.copilot/softwareFactoryVscode/.tmp/\n.copilot/softwareFactoryVscode/.factory.env\n",
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
                    {
                        "name": "AI Agent Factory",
                        "path": ".copilot/softwareFactoryVscode",
                    },
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
        verify_factory_install.factory_stack.shutil,
        "which",
        lambda name: "/usr/bin/docker",
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "collect_service_inventory",
        lambda _name: build_full_service_inventory(config),
    )
    stub_runtime_manager_with_successful_probes(
        monkeypatch,
        verify_factory_install.factory_stack,
        registry_path=registry_path,
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: probed_urls.append(url) or None,
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert violations == []
    assert probed_urls
    assert all("9090" not in url for url in probed_urls)


def test_verify_runtime_requires_manager_snapshot_contract_when_preflight_is_ready(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "issues": [],
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "verify_runtime should fail closed before running additive probes when the snapshot contract is missing"
            )
        ),
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert violations == [
        "Runtime preflight reported `ready` but did not provide a manager-backed "
        "snapshot, so runtime verification cannot continue authoritatively."
    ]


def test_verify_runtime_prefers_manager_snapshot_probe_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "PORT_CONTEXT7=3010",
                "MEMORY_MCP_PORT=3030",
                "AGENT_BUS_PORT=3031",
                "APPROVAL_GATE_PORT=8001",
                "PORT_TUI=9090",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    services = {}
    for service_name, metadata in verify_factory_install.RUNTIME_SERVICES.items():
        probe_url = ""
        if metadata["health_path"]:
            probe_url = f"http://snapshot.example/{service_name}"
        services[service_name] = build_snapshot_service_record(
            probe_url=probe_url,
        )

    snapshot = build_runtime_snapshot_contract(
        services=services,
    )
    probed_urls: list[str] = []

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "snapshot": snapshot,
            "readiness": snapshot.readiness,
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: probed_urls.append(url) or None,
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert violations == []
    assert probed_urls
    assert all(url.startswith("http://snapshot.example/") for url in probed_urls)
    assert "http://127.0.0.1:3030/mcp" not in probed_urls


def test_verify_runtime_reports_preflight_status_and_action_for_drift(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "config-drift",
            "recommended_action": "re-bootstrap",
            "reason_codes": ["workspace-url-drift"],
            "issues": [
                (
                    "Generated workspace MCP URL drift detected for `context7` "
                    "(expected `http://127.0.0.1:3210/mcp`, found "
                    "`http://127.0.0.1:3010/mcp`)."
                )
            ],
            "service_inventory": {},
            "workspace_urls": {},
        },
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=True,
    )

    assert (
        violations[0] == "Runtime preflight reported `config-drift` "
        "(recommended_action=`re-bootstrap`). reason_codes=`workspace-url-drift`."
    )
    assert any(
        "Generated workspace MCP URL drift detected" in violation
        for violation in violations
    )


def test_verify_runtime_uses_shared_service_discovery_when_shared_mode_enabled(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "FACTORY_SHARED_SERVICE_MODE=shared",
                "FACTORY_TENANCY_MODE=shared",
                "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    shared_service_probe_urls = {
        "mcp-memory": "http://shared-memory.internal:3030/mcp",
        "mcp-agent-bus": "http://shared-bus.internal:3031/mcp",
        "approval-gate": "http://shared-approval.internal:8001/health",
    }
    services = {}
    for service_name, metadata in verify_factory_install.RUNTIME_SERVICES.items():
        probe_url = shared_service_probe_urls.get(service_name, "")
        if not probe_url and metadata["health_path"]:
            probe_url = f"http://snapshot.example/{service_name}"
        services[service_name] = build_snapshot_service_record(
            workspace_owned=service_name not in shared_service_probe_urls,
            probe_url=probe_url,
        )

    snapshot = build_runtime_snapshot_contract(
        shared_mode_diagnostics={
            "shared_mode_configured": True,
            "tenant_identity_required": True,
            "expected_tenant_identity": "target-project",
            "tenant_identity_header": "X-Workspace-ID",
        },
        services=services,
    )

    probed_urls: list[str] = []
    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "snapshot": snapshot,
            "readiness": snapshot.readiness,
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: probed_urls.append(url) or None,
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert violations == []
    assert "http://shared-memory.internal:3030/mcp" in probed_urls
    assert "http://shared-bus.internal:3031/mcp" in probed_urls
    assert "http://shared-approval.internal:8001/health" in probed_urls


def test_verify_runtime_reports_missing_tenant_identity_for_shared_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "FACTORY_SHARED_SERVICE_MODE=shared",
                "FACTORY_TENANCY_MODE=shared",
                "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    shared_service_probe_urls = {
        "mcp-memory": "http://shared-memory.internal:3030/mcp",
        "mcp-agent-bus": "http://shared-bus.internal:3031/mcp",
        "approval-gate": "http://shared-approval.internal:8001/health",
    }
    services = {}
    for service_name, metadata in verify_factory_install.RUNTIME_SERVICES.items():
        probe_url = shared_service_probe_urls.get(service_name, "")
        if not probe_url and metadata["health_path"]:
            probe_url = f"http://snapshot.example/{service_name}"
        services[service_name] = build_snapshot_service_record(
            workspace_owned=service_name not in shared_service_probe_urls,
            probe_url=probe_url,
        )

    snapshot = build_runtime_snapshot_contract(
        shared_mode_diagnostics={
            "shared_mode_configured": True,
            "tenant_identity_required": True,
            "expected_tenant_identity": "target-project",
            "tenant_identity_header": "X-Workspace-ID",
            "missing_tenant_remediation": "Send X-Workspace-ID=target-project from workspace clients.",
        },
        services=services,
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "snapshot": snapshot,
            "readiness": snapshot.readiness,
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: (
            "Promoted shared mode requires an explicit tenant identity via "
            "X-Workspace-ID or another explicit tenant selector."
            if "shared-memory.internal" in url
            else None
        ),
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert any(
        "no explicit tenant identity was supplied" in violation
        for violation in violations
    )
    assert any(
        "X-Workspace-ID: target-project" in violation for violation in violations
    )


def test_verify_runtime_reports_tenant_mismatch_for_shared_probe(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    env_path.write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "FACTORY_SHARED_SERVICE_MODE=shared",
                "FACTORY_TENANCY_MODE=shared",
                "FACTORY_SHARED_MEMORY_URL=http://shared-memory.internal:3030",
                "FACTORY_SHARED_AGENT_BUS_URL=http://shared-bus.internal:3031",
                "FACTORY_SHARED_APPROVAL_GATE_URL=http://shared-approval.internal:8001",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    shared_service_probe_urls = {
        "mcp-memory": "http://shared-memory.internal:3030/mcp",
        "mcp-agent-bus": "http://shared-bus.internal:3031/mcp",
        "approval-gate": "http://shared-approval.internal:8001/health",
    }
    services = {}
    for service_name, metadata in verify_factory_install.RUNTIME_SERVICES.items():
        probe_url = shared_service_probe_urls.get(service_name, "")
        if not probe_url and metadata["health_path"]:
            probe_url = f"http://snapshot.example/{service_name}"
        services[service_name] = build_snapshot_service_record(
            workspace_owned=service_name not in shared_service_probe_urls,
            probe_url=probe_url,
        )

    snapshot = build_runtime_snapshot_contract(
        shared_mode_diagnostics={
            "shared_mode_configured": True,
            "tenant_identity_required": True,
            "expected_tenant_identity": "target-project",
            "tenant_identity_header": "X-Workspace-ID",
            "tenant_mismatch_remediation": "Align explicit selectors to target-project.",
        },
        services=services,
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "ready",
            "recommended_action": "none",
            "snapshot": snapshot,
            "readiness": snapshot.readiness,
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda url, timeout, allow_http_error: (
            "Tenant identity mismatch across explicit selectors: X-Workspace-ID=tenant-a, project_id=tenant-b."
            if "shared-bus.internal" in url
            else None
        ),
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=False,
    )

    assert any(
        "observed tenant selectors do not match" in violation
        for violation in violations
    )
    assert any("target-project" in violation for violation in violations)
    assert any("project_id=tenant-b" in violation for violation in violations)


def test_verify_runtime_short_circuits_on_preflight_issues(
    tmp_path: Path,
    monkeypatch,
) -> None:
    target_repo = tmp_path / "target-project"
    target_repo.mkdir(parents=True, exist_ok=True)
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (target_repo / ".copilot/softwareFactoryVscode/.factory.env").write_text(
        "\n".join(
            [
                f"TARGET_WORKSPACE_PATH={target_repo}",
                f"FACTORY_DIR={factory_dir}",
                "PROJECT_WORKSPACE_ID=target-project",
                "COMPOSE_PROJECT_NAME=factory_target-project",
                "CONTEXT7_API_KEY=",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        verify_factory_install.shutil, "which", lambda name: "/usr/bin/docker"
    )
    monkeypatch.setattr(
        verify_factory_install.factory_stack,
        "build_preflight_report",
        lambda *_args, **_kwargs: {
            "status": "needs-ramp-up",
            "issues": ["Runtime preflight detected no running containers."],
            "service_inventory": {},
            "workspace_urls": {},
        },
    )
    monkeypatch.setattr(
        verify_factory_install,
        "probe_http_url",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                "probe_http_url should not be called before preflight passes"
            )
        ),
    )

    violations = verify_factory_install.verify_runtime(
        target_repo,
        workspace_file="software-factory.code-workspace",
        timeout=1.0,
        check_vscode_mcp=True,
    )

    assert violations == [
        "Runtime preflight reported `needs-ramp-up`.",
        "Runtime preflight detected no running containers.",
    ]


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
    env_file = repo_root / ".factory.env"
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


def test_runtime_compose_shared_services_expose_tenancy_mode_switch() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    expected = "${FACTORY_TENANCY_MODE:-compatibility}"

    assert (
        services.get("mcp-memory", {})
        .get("environment", {})
        .get("FACTORY_TENANCY_MODE")
        == expected
    )
    assert (
        services.get("mcp-agent-bus", {})
        .get("environment", {})
        .get("FACTORY_TENANCY_MODE")
        == expected
    )
    assert (
        services.get("approval-gate", {})
        .get("environment", {})
        .get("FACTORY_TENANCY_MODE")
        == expected
    )

    shared_topology_expected = "${FACTORY_SHARED_SERVICE_MODE:-per-workspace}"

    assert (
        services.get("mcp-memory", {})
        .get("environment", {})
        .get("FACTORY_SHARED_SERVICE_MODE")
        == shared_topology_expected
    )
    assert (
        services.get("mcp-agent-bus", {})
        .get("environment", {})
        .get("FACTORY_SHARED_SERVICE_MODE")
        == shared_topology_expected
    )
    assert (
        services.get("approval-gate", {})
        .get("environment", {})
        .get("FACTORY_SHARED_SERVICE_MODE")
        == shared_topology_expected
    )


def test_runtime_compose_interservice_urls_use_fixed_internal_ports() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.factory.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    approval_env = services.get("approval-gate", {}).get("environment", {})
    worker_env = services.get("agent-worker", {}).get("environment", {})

    assert (
        approval_env.get("AGENT_BUS_URL")
        == "${FACTORY_SHARED_AGENT_BUS_URL:-http://mcp-agent-bus:3031}"
    )
    assert (
        worker_env.get("MEMORY_MCP_URL")
        == "${FACTORY_SHARED_MEMORY_URL:-http://mcp-memory:3030}"
    )
    assert (
        worker_env.get("AGENT_BUS_URL")
        == "${FACTORY_SHARED_AGENT_BUS_URL:-http://mcp-agent-bus:3031}"
    )
    assert (
        worker_env.get("APPROVAL_GATE_URL")
        == "${FACTORY_SHARED_APPROVAL_GATE_URL:-http://approval-gate:8001}"
    )


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


def test_devops_mcp_compose_host_ports_match_workspace_port_contract() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.mcp-devops.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    docker_ports = services.get("docker-compose-mcp", {}).get("ports", [])
    test_runner_ports = services.get("test-runner-mcp", {}).get("ports", [])

    assert docker_ports == [
        f"127.0.0.1:${{PORT_COMPOSE:-{factory_workspace.PORT_LAYOUT['PORT_COMPOSE']}}}:3015"
    ]
    assert test_runner_ports == [
        f"127.0.0.1:${{PORT_TEST:-{factory_workspace.PORT_LAYOUT['PORT_TEST']}}}:3016"
    ]


def test_devops_mcp_healthchecks_use_python3() -> None:
    compose_file = REPO_ROOT / "compose" / "docker-compose.mcp-devops.yml"
    data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    services = data.get("services", {})

    for service_name in ("docker-compose-mcp", "test-runner-mcp"):
        healthcheck = services.get(service_name, {}).get("healthcheck", {})
        test_cmd = healthcheck.get("test", [])
        assert isinstance(test_cmd, list)
        assert "python3" in test_cmd


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
    (ephemeral_target / ".copilot/softwareFactoryVscode/.tmp").mkdir(
        parents=True, exist_ok=True
    )
    (
        ephemeral_target
        / ".copilot/softwareFactoryVscode/.tmp"
        / "runtime-manifest.json"
    ).write_text(
        json.dumps(
            {
                "factory_instance_id": "factory-ephemeral",
                "target_workspace_path": str(ephemeral_target),
                "ports": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    persistent_target = Path("/tmp") / "factory-registry-persistent-target"
    if persistent_target.exists():
        shutil.rmtree(persistent_target)
    persistent_target.mkdir(parents=True, exist_ok=True)
    try:
        (persistent_target / ".copilot/softwareFactoryVscode/.tmp").mkdir(
            parents=True, exist_ok=True
        )
        (
            persistent_target
            / ".copilot"
            / "softwareFactoryVscode"
            / ".tmp"
            / "runtime-manifest.json"
        ).write_text(
            json.dumps(
                {
                    "factory_instance_id": "factory-persistent",
                    "target_workspace_path": str(persistent_target),
                    "ports": {},
                }
            )
            + "\n",
            encoding="utf-8",
        )

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


def test_reconcile_registry_prunes_existing_non_managed_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))

    invalid_target = tmp_path / "home-sw-like"
    invalid_target.mkdir(parents=True, exist_ok=True)

    factory_workspace.write_json_atomic(
        registry_path,
        {
            "version": 1,
            "active_workspace": "factory-invalid",
            "workspaces": {
                "factory-invalid": {
                    "factory_instance_id": "factory-invalid",
                    "project_workspace_id": "invalid",
                    "target_workspace_path": str(invalid_target),
                    "port_index": 0,
                    "ports": factory_workspace.build_port_values(0),
                    "runtime_state": "installed",
                }
            },
        },
    )

    result = factory_workspace.reconcile_registry(registry_path=registry_path)
    updated = factory_workspace.load_registry(registry_path=registry_path)

    assert "factory-invalid" in result["stale_removed"]
    assert "factory-invalid" in result["invalid_targets_removed"]
    assert updated["active_workspace"] == ""
    assert updated["workspaces"] == {}


def test_build_runtime_config_reconciles_stale_missing_registry_entries_before_allocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    stale_registry = {
        "version": 1,
        "active_workspace": "",
        "workspaces": {},
    }
    for index in range(200):
        instance_id = f"factory-stale-{index}"
        stale_registry["workspaces"][instance_id] = {
            "factory_instance_id": instance_id,
            "project_workspace_id": f"stale-{index}",
            "target_workspace_path": str(tmp_path / f"missing-target-{index}"),
            "port_index": index,
            "ports": factory_workspace.build_port_values(index),
            "runtime_state": "installed",
        }
    factory_workspace.write_json_atomic(registry_path, stale_registry)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    registry_after = factory_workspace.load_registry(registry_path=registry_path)

    assert config.port_index == 0
    assert registry_after.get("workspaces", {}) == {}


def test_bootstrap_sync_runtime_contract_recovers_from_stale_registry_exhaustion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)
    monkeypatch.setattr(
        bootstrap_host.factory_workspace,
        "ports_available",
        lambda ports: True,
    )

    stale_registry = {
        "version": 1,
        "active_workspace": "",
        "workspaces": {},
    }
    for index in range(200):
        instance_id = f"factory-stale-{index}"
        stale_registry["workspaces"][instance_id] = {
            "factory_instance_id": instance_id,
            "project_workspace_id": f"stale-{index}",
            "target_workspace_path": str(tmp_path / f"gone-{index}"),
            "port_index": index,
            "ports": factory_workspace.build_port_values(index),
            "runtime_state": "installed",
        }
    factory_workspace.write_json_atomic(registry_path, stale_registry)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config, factory_env_created = bootstrap_host.sync_factory_runtime_contract(
        target_repo,
        workspace_file="software-factory.code-workspace",
    )
    registry_after = factory_workspace.load_registry(registry_path=registry_path)

    assert factory_env_created is True
    assert config.port_index == 0
    assert set(registry_after.get("workspaces", {}).keys()) == {
        config.factory_instance_id
    }


def test_refresh_registry_entry_rebuilds_missing_record_from_local_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="installed",
        active=False,
    )

    runtime_manifest_path = config.runtime_manifest_path
    runtime_manifest_path.unlink()
    factory_workspace.write_json_atomic(
        registry_path,
        {
            "version": 1,
            "active_workspace": "",
            "workspaces": {},
        },
    )

    factory_workspace.refresh_registry_entry(target_repo, registry_path=registry_path)

    updated = factory_workspace.load_registry(registry_path=registry_path)
    assert config.factory_instance_id in updated.get("workspaces", {})
    assert runtime_manifest_path.exists()
    rebuilt_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8"))
    assert rebuilt_manifest["factory_instance_id"] == config.factory_instance_id


def test_reconcile_registry_recovers_mismatched_instance_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
    monkeypatch.setattr(factory_workspace, "ports_available", lambda ports: True)

    target_repo = tmp_path / "target-project"
    factory_dir = target_repo / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config").mkdir(parents=True, exist_ok=True)
    (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
        (REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    config = factory_workspace.build_runtime_config(
        target_repo, factory_dir=factory_dir
    )
    factory_workspace.sync_runtime_artifacts(
        config,
        runtime_state="running",
        active=True,
    )

    stale_id = "factory-stale-alias"
    registry = factory_workspace.load_registry(registry_path=registry_path)
    stale_record = registry["workspaces"].pop(config.factory_instance_id)
    stale_record["factory_instance_id"] = stale_id
    registry["workspaces"][stale_id] = stale_record
    registry["active_workspace"] = stale_id
    factory_workspace.write_json_atomic(registry_path, registry)

    result = factory_workspace.reconcile_registry(registry_path=registry_path)
    updated = factory_workspace.load_registry(registry_path=registry_path)

    assert stale_id in result["recovered_ids"]
    assert config.factory_instance_id in updated["workspaces"]
    assert stale_id not in updated["workspaces"]
    assert updated["active_workspace"] == config.factory_instance_id
    assert (
        updated["workspaces"][config.factory_instance_id]["runtime_state"] == "running"
    )


def test_reconcile_registry_rejects_conflicting_port_ownership(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))

    target_a = Path("/tmp") / "factory-registry-conflict-a"
    target_b = Path("/tmp") / "factory-registry-conflict-b"
    for target in (target_a, target_b):
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

    target_a_manifest_path = (
        target_a / ".copilot/softwareFactoryVscode/.tmp/runtime-manifest.json"
    )
    target_b_manifest_path = (
        target_b / ".copilot/softwareFactoryVscode/.tmp/runtime-manifest.json"
    )
    target_a_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    target_b_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    shared_ports = factory_workspace.build_port_values(0)
    manifest_a = {
        "factory_instance_id": "factory-a",
        "project_workspace_id": "project-a",
        "target_workspace_path": str(target_a),
        "factory_dir": str(target_a / ".copilot/softwareFactoryVscode"),
        "workspace_file_path": str(target_a / "software-factory.code-workspace"),
        "compose_project_name": "factory_project-a",
        "port_index": 0,
        "ports": shared_ports,
        "factory_version": "test",
        "factory_display_version": "test+local",
        "factory_release": {"commit_sha": "a" * 40},
    }
    manifest_b = {
        "factory_instance_id": "factory-b",
        "project_workspace_id": "project-b",
        "target_workspace_path": str(target_b),
        "factory_dir": str(target_b / ".copilot/softwareFactoryVscode"),
        "workspace_file_path": str(target_b / "software-factory.code-workspace"),
        "compose_project_name": "factory_project-b",
        "port_index": 0,
        "ports": shared_ports,
        "factory_version": "test",
        "factory_display_version": "test+local",
        "factory_release": {"commit_sha": "b" * 40},
    }
    target_a_manifest_path.write_text(
        json.dumps(manifest_a, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    target_b_manifest_path.write_text(
        json.dumps(manifest_b, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    factory_workspace.write_json_atomic(
        registry_path,
        {
            "version": 1,
            "active_workspace": "",
            "workspaces": {
                "factory-a": {
                    "factory_instance_id": "factory-a",
                    "target_workspace_path": str(target_a),
                    "runtime_state": "installed",
                    "ports": shared_ports,
                },
                "factory-b": {
                    "factory_instance_id": "factory-b",
                    "target_workspace_path": str(target_b),
                    "runtime_state": "installed",
                    "ports": shared_ports,
                },
            },
        },
    )

    try:
        try:
            factory_workspace.reconcile_registry(registry_path=registry_path)
        except RuntimeError as exc:
            assert "Port ownership conflict" in str(exc)
        else:
            raise AssertionError(
                "Expected reconciliation to fail on duplicate port ownership"
            )
    finally:
        shutil.rmtree(target_a, ignore_errors=True)
        shutil.rmtree(target_b, ignore_errors=True)


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


def test_factory_orchestrator_uses_manager_backed_runtime_accessors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    workspace_root = tmp_path / "target"
    workspace_root.mkdir(parents=True, exist_ok=True)

    class FakeRuntimeManager:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def load_workspace_id(self, workspace_root_arg: Path) -> str | None:
            self.calls.append(("load_workspace_id", workspace_root_arg))
            return "manager-workspace"

        def load_named_urls_from_workspace(
            self,
            workspace_root_arg: Path,
            mappings: dict[str, tuple[str, str]],
            *,
            selected_profiles=None,
        ) -> dict[str, str]:
            normalized_profiles = tuple(
                getattr(profile, "value", str(profile))
                for profile in (selected_profiles or ())
            )
            self.calls.append(
                (
                    "load_named_urls_from_workspace",
                    workspace_root_arg,
                    tuple(sorted(mappings.keys())),
                    normalized_profiles,
                )
            )
            return {
                "mcp-memory": "http://manager.example/memory",
                "mcp-agent-bus": "http://manager.example/bus",
                "mcp-github-ops": "http://manager.example/github",
                "mcp-search": "http://manager.example/search",
                "mcp-filesystem": "http://manager.example/filesystem",
            }

    fake_manager = FakeRuntimeManager()
    monkeypatch.delenv("PROJECT_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("FACTORY_MEMORY_URL", raising=False)
    monkeypatch.delenv("FACTORY_BUS_URL", raising=False)
    monkeypatch.delenv("FACTORY_GITHUB_URL", raising=False)
    monkeypatch.delenv("FACTORY_SEARCH_URL", raising=False)
    monkeypatch.delenv("FACTORY_FILESYSTEM_URL", raising=False)
    monkeypatch.setattr(
        factory_agents,
        "_build_runtime_manager",
        lambda: fake_manager,
    )

    workspace_id = factory_agents._load_workspace_id(workspace_root)
    server_urls = factory_agents._load_server_urls(workspace_root)

    assert workspace_id == "manager-workspace"
    assert server_urls == {
        "mcp-memory": "http://manager.example/memory",
        "mcp-agent-bus": "http://manager.example/bus",
        "mcp-github-ops": "http://manager.example/github",
        "mcp-search": "http://manager.example/search",
        "mcp-filesystem": "http://manager.example/filesystem",
    }
    assert fake_manager.calls == [
        ("load_workspace_id", workspace_root),
        (
            "load_named_urls_from_workspace",
            workspace_root,
            (
                "mcp-agent-bus",
                "mcp-filesystem",
                "mcp-github-ops",
                "mcp-memory",
                "mcp-search",
            ),
            ("harness-default",),
        ),
    ]


def test_devops_docker_compose_image_installs_docker_compose_plugin_on_debian() -> None:
    dockerfile = REPO_ROOT / "docker" / "mcp-devops-docker-compose" / "Dockerfile"

    text = dockerfile.read_text(encoding="utf-8")

    assert "FROM python:3.12-slim-bookworm" in text
    assert "docker-ce-cli" in text
    assert "docker-compose-plugin" in text
    assert "apk add" not in text
    assert "FROM docker:27.4.1-cli" not in text


def test_factory_orchestrator_loads_generated_runtime_manifest_urls(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    manifest_path = (
        target / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "githubOps": {"url": "http://127.0.0.1:21818/mcp"},
                    "search": {"url": "http://127.0.0.1:21813/mcp"},
                    "filesystem": {"url": "http://127.0.0.1:21814/mcp"},
                },
                "runtime_health": {
                    "mcp-memory": {"url": "http://127.0.0.1:21830/mcp"},
                    "mcp-agent-bus": {"url": "http://127.0.0.1:21831/mcp"},
                },
            }
        ),
        encoding="utf-8",
    )

    server_urls = factory_agents._load_server_urls(target)

    assert server_urls == {
        "mcp-memory": "http://127.0.0.1:21830/mcp",
        "mcp-agent-bus": "http://127.0.0.1:21831/mcp",
        "mcp-github-ops": "http://127.0.0.1:21818/mcp",
        "mcp-search": "http://127.0.0.1:21813/mcp",
        "mcp-filesystem": "http://127.0.0.1:21814/mcp",
    }


def test_factory_orchestrator_loads_companion_runtime_manifest_for_source_checkout(
    tmp_path: Path,
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    manifest_path = (
        tmp_path / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "githubOps": {"url": "http://127.0.0.1:21818/mcp"},
                    "search": {"url": "http://127.0.0.1:21813/mcp"},
                    "filesystem": {"url": "http://127.0.0.1:21814/mcp"},
                },
                "runtime_health": {
                    "mcp-memory": {"url": "http://127.0.0.1:21830/mcp"},
                    "mcp-agent-bus": {"url": "http://127.0.0.1:21831/mcp"},
                },
            }
        ),
        encoding="utf-8",
    )

    server_urls = factory_agents._load_server_urls(source_repo)

    assert server_urls == {
        "mcp-memory": "http://127.0.0.1:21830/mcp",
        "mcp-agent-bus": "http://127.0.0.1:21831/mcp",
        "mcp-github-ops": "http://127.0.0.1:21818/mcp",
        "mcp-search": "http://127.0.0.1:21813/mcp",
        "mcp-filesystem": "http://127.0.0.1:21814/mcp",
    }


def test_mcp_bootloader_uses_manager_backed_snapshot_when_workspace_is_source_repo(
    tmp_path: Path, monkeypatch
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    companion_env = tmp_path / ".copilot" / "softwareFactoryVscode" / ".factory.env"
    companion_env.parent.mkdir(parents=True, exist_ok=True)
    companion_env.write_text("TARGET_WORKSPACE_PATH=/tmp/demo\n", encoding="utf-8")

    readiness = SimpleNamespace(
        ready=True,
        status=SimpleNamespace(value="ready"),
        recommended_action=mcp_lifecycle.RecommendedAction.NONE,
        issues=(),
    )
    snapshot = SimpleNamespace(
        lifecycle_state=mcp_lifecycle.RuntimeLifecycleState.RUNNING,
        readiness=readiness,
        manifest_server_urls={
            "githubOps": "http://127.0.0.1:21818/mcp",
            "search": "http://127.0.0.1:21813/mcp",
            "filesystem": "http://127.0.0.1:21814/mcp",
        },
        manifest_health_urls={
            "mcp-memory": "http://127.0.0.1:21830/mcp",
            "mcp-agent-bus": "http://127.0.0.1:21831/mcp",
        },
    )

    class FakeRuntimeManager:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def resolve_factory_repo_root(self, workspace_root: Path) -> Path:
            self.calls.append(("resolve_factory_repo_root", workspace_root))
            return source_repo.resolve()

        def resolve_workspace_env_file(
            self,
            workspace_root: Path,
            factory_repo_root: Path | None = None,
        ) -> Path:
            self.calls.append(
                (
                    "resolve_workspace_env_file",
                    workspace_root,
                    factory_repo_root,
                )
            )
            return companion_env.resolve()

        def build_workspace_snapshot(
            self,
            workspace_root: Path,
            *,
            workspace_file: str | None = None,
            selected_profiles=None,
        ) -> Any:
            normalized_profiles = tuple(
                getattr(profile, "value", str(profile))
                for profile in (selected_profiles or ())
            )
            self.calls.append(
                (
                    "build_workspace_snapshot",
                    workspace_root,
                    workspace_file,
                    normalized_profiles,
                )
            )
            return snapshot

        def start(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("ready runtime should not trigger manager.start")

        def stop(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("teardown is not part of this regression test")

    fake_manager = FakeRuntimeManager()
    bootloader = mcp_lifecycle.MCPBootloader(source_repo)
    monkeypatch.setattr(
        bootloader,
        "_build_runtime_manager",
        lambda: fake_manager,
    )

    asyncio.run(bootloader.initialize())

    assert fake_manager.calls == [
        ("resolve_factory_repo_root", source_repo),
        (
            "resolve_workspace_env_file",
            source_repo,
            source_repo.resolve(),
        ),
        (
            "build_workspace_snapshot",
            source_repo,
            None,
            ("harness-default",),
        ),
    ]
    assert bootloader.server_urls == {
        "mcp-memory": "http://127.0.0.1:21830/mcp",
        "mcp-agent-bus": "http://127.0.0.1:21831/mcp",
        "mcp-github-ops": "http://127.0.0.1:21818/mcp",
        "mcp-search": "http://127.0.0.1:21813/mcp",
        "mcp-filesystem": "http://127.0.0.1:21814/mcp",
    }


def test_mcp_bootloader_resumes_bounded_suspended_runtime(
    tmp_path: Path, monkeypatch
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    companion_env = tmp_path / ".copilot" / "softwareFactoryVscode" / ".factory.env"
    companion_env.parent.mkdir(parents=True, exist_ok=True)
    companion_env.write_text("TARGET_WORKSPACE_PATH=/tmp/demo\n", encoding="utf-8")

    suspended_snapshot = SimpleNamespace(
        lifecycle_state=mcp_lifecycle.RuntimeLifecycleState.SUSPENDED,
        readiness=SimpleNamespace(
            ready=False,
            status=SimpleNamespace(value="needs-ramp-up"),
            recommended_action=mcp_lifecycle.RecommendedAction.RESUME,
            issues=(),
        ),
        manifest_server_urls={
            "githubOps": "http://127.0.0.1:29618/mcp",
            "search": "http://127.0.0.1:29613/mcp",
            "filesystem": "http://127.0.0.1:29614/mcp",
        },
        manifest_health_urls={
            "mcp-memory": "http://127.0.0.1:29630/mcp",
            "mcp-agent-bus": "http://127.0.0.1:29631/mcp",
        },
    )
    resumed_snapshot = SimpleNamespace(
        lifecycle_state=mcp_lifecycle.RuntimeLifecycleState.RUNNING,
        readiness=SimpleNamespace(
            ready=True,
            status=SimpleNamespace(value="ready"),
            recommended_action=mcp_lifecycle.RecommendedAction.NONE,
            issues=(),
        ),
        manifest_server_urls={
            "githubOps": "http://127.0.0.1:29618/mcp",
            "search": "http://127.0.0.1:29613/mcp",
            "filesystem": "http://127.0.0.1:29614/mcp",
        },
        manifest_health_urls={
            "mcp-memory": "http://127.0.0.1:29630/mcp",
            "mcp-agent-bus": "http://127.0.0.1:29631/mcp",
        },
    )

    class FakeRuntimeManager:
        def __init__(self) -> None:
            self.calls: list[tuple[Any, ...]] = []

        def resolve_factory_repo_root(self, workspace_root: Path) -> Path:
            self.calls.append(("resolve_factory_repo_root", workspace_root))
            return source_repo.resolve()

        def resolve_workspace_env_file(
            self,
            workspace_root: Path,
            factory_repo_root: Path | None = None,
        ) -> Path:
            self.calls.append(
                (
                    "resolve_workspace_env_file",
                    workspace_root,
                    factory_repo_root,
                )
            )
            return companion_env.resolve()

        def build_workspace_snapshot(
            self,
            workspace_root: Path,
            *,
            workspace_file: str | None = None,
            selected_profiles=None,
        ) -> Any:
            normalized_profiles = tuple(
                getattr(profile, "value", str(profile))
                for profile in (selected_profiles or ())
            )
            self.calls.append(
                (
                    "build_workspace_snapshot",
                    workspace_root,
                    workspace_file,
                    normalized_profiles,
                )
            )
            return suspended_snapshot

        def resume(
            self,
            repo_root: Path,
            *,
            env_file: Path | None = None,
            selected_profiles=None,
        ) -> Any:
            normalized_profiles = tuple(
                getattr(profile, "value", str(profile))
                for profile in (selected_profiles or ())
            )
            self.calls.append(("resume", repo_root, env_file, normalized_profiles))
            return resumed_snapshot

        def start(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("suspended runtime should call manager.resume")

        def stop(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("teardown is not part of this regression test")

    fake_manager = FakeRuntimeManager()
    bootloader = mcp_lifecycle.MCPBootloader(source_repo)
    monkeypatch.setattr(
        bootloader,
        "_build_runtime_manager",
        lambda: fake_manager,
    )

    asyncio.run(bootloader.initialize())

    assert fake_manager.calls == [
        ("resolve_factory_repo_root", source_repo),
        (
            "resolve_workspace_env_file",
            source_repo,
            source_repo.resolve(),
        ),
        (
            "build_workspace_snapshot",
            source_repo,
            None,
            ("harness-default",),
        ),
        (
            "resume",
            source_repo.resolve(),
            companion_env.resolve(),
            ("harness-default",),
        ),
    ]
    assert bootloader.server_urls == {
        "mcp-memory": "http://127.0.0.1:29630/mcp",
        "mcp-agent-bus": "http://127.0.0.1:29631/mcp",
        "mcp-github-ops": "http://127.0.0.1:29618/mcp",
        "mcp-search": "http://127.0.0.1:29613/mcp",
        "mcp-filesystem": "http://127.0.0.1:29614/mcp",
    }


def test_mcp_bootloader_requires_snapshot_readiness_contract(
    tmp_path: Path, monkeypatch
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    companion_env = tmp_path / ".copilot" / "softwareFactoryVscode" / ".factory.env"
    companion_env.parent.mkdir(parents=True, exist_ok=True)
    companion_env.write_text("TARGET_WORKSPACE_PATH=/tmp/demo\n", encoding="utf-8")

    snapshot = SimpleNamespace(
        readiness=None,
        manifest_server_urls={
            "githubOps": "http://127.0.0.1:21818/mcp",
            "search": "http://127.0.0.1:21813/mcp",
            "filesystem": "http://127.0.0.1:21814/mcp",
        },
        manifest_health_urls={
            "mcp-memory": "http://127.0.0.1:21830/mcp",
            "mcp-agent-bus": "http://127.0.0.1:21831/mcp",
        },
    )

    class FakeRuntimeManager:
        def resolve_factory_repo_root(self, workspace_root: Path) -> Path:
            assert workspace_root == source_repo
            return source_repo.resolve()

        def resolve_workspace_env_file(
            self,
            workspace_root: Path,
            factory_repo_root: Path | None = None,
        ) -> Path:
            assert workspace_root == source_repo
            assert factory_repo_root == source_repo.resolve()
            return companion_env.resolve()

        def build_workspace_snapshot(
            self,
            workspace_root: Path,
            *,
            workspace_file: str | None = None,
            selected_profiles=None,
        ) -> Any:
            assert workspace_root == source_repo
            del workspace_file, selected_profiles
            return snapshot

        def start(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("invalid readiness contract should fail before start")

    bootloader = mcp_lifecycle.MCPBootloader(source_repo)
    monkeypatch.setattr(
        bootloader,
        "_build_runtime_manager",
        lambda: FakeRuntimeManager(),
    )

    with pytest.raises(RuntimeError, match="readiness result"):
        asyncio.run(bootloader.initialize())


def test_mcp_bootloader_teardown_keeps_runtime_running_by_default(
    tmp_path: Path,
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    env_file = source_repo / ".factory.env"
    stop_calls: list[tuple[Path, Path | None]] = []

    class FakeRuntimeManager:
        def stop(self, repo_root: Path, *, env_file: Path | None = None) -> None:
            stop_calls.append((repo_root, env_file))

    bootloader = mcp_lifecycle.MCPBootloader(source_repo)
    bootloader._runtime_manager = FakeRuntimeManager()
    bootloader._factory_repo_root = source_repo
    bootloader._env_file = env_file

    bootloader.teardown()
    bootloader.teardown()

    assert stop_calls == []


def test_mcp_bootloader_teardown_stops_runtime_only_when_requested(
    tmp_path: Path,
) -> None:
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    env_file = source_repo / ".factory.env"
    stop_calls: list[tuple[Path, Path | None]] = []

    class FakeRuntimeManager:
        def stop(self, repo_root: Path, *, env_file: Path | None = None) -> None:
            stop_calls.append((repo_root, env_file))

    bootloader = mcp_lifecycle.MCPBootloader(
        source_repo,
        kill_mcps_on_exit=True,
    )
    bootloader._runtime_manager = FakeRuntimeManager()
    bootloader._factory_repo_root = source_repo
    bootloader._env_file = env_file

    bootloader.teardown()
    bootloader.teardown()

    assert stop_calls == [(source_repo, env_file)]


def test_cleanup_workspace(tmp_path: Path, monkeypatch, capsys):
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))
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

    config = factory_workspace.build_runtime_config(target, factory_dir=factory_dir)
    factory_workspace.sync_runtime_artifacts(config)
    assert (data_root / "memory" / config.factory_instance_id).is_dir()
    assert (data_root / "bus" / config.factory_instance_id).is_dir()

    # Assert created
    assert (target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert (
        target / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    ).exists()

    # cleanup
    factory_stack.cleanup_workspace(
        factory_dir, env_file=(target / ".copilot/softwareFactoryVscode/.factory.env")
    )
    output = capsys.readouterr().out

    assert not (target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert not (
        target / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    ).exists()
    assert not (data_root / "memory" / config.factory_instance_id).exists()
    assert not (data_root / "bus" / config.factory_instance_id).exists()

    reg = factory_workspace.load_registry(registry_path)
    assert config.factory_instance_id in reg.get("workspaces", {})
    record = reg["workspaces"][config.factory_instance_id]
    assert record["runtime_state"] == "runtime-deleted"
    assert record["last_runtime_action"] == "cleanup"
    assert record["last_completed_tool_call_boundary_at"]
    assert (
        "`cleanup` removed workspace containers and named volumes when present"
        in output
    )
    assert "Docker images were retained" in output


def test_delete_runtime_matches_cleanup_artifact_effects_with_distinct_trigger_metadata(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    registry_path = tmp_path / "registry.json"
    monkeypatch.setenv("SOFTWARE_FACTORY_REGISTRY_PATH", str(registry_path))

    def _prepare_runtime(workspace_name: str) -> tuple[Path, Path, Path, Any]:
        target = tmp_path / workspace_name
        target.mkdir(parents=True, exist_ok=True)
        factory_dir = target / ".copilot/softwareFactoryVscode"
        factory_dir.mkdir(parents=True, exist_ok=True)
        (factory_dir / ".copilot" / "config").mkdir(parents=True)
        (factory_dir / ".copilot" / "config" / "vscode-agent-settings.json").write_text(
            (
                REPO_ROOT / ".copilot" / "config" / "vscode-agent-settings.json"
            ).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        data_root = tmp_path / f"factory-data-{workspace_name}"
        env_path = factory_dir / ".factory.env"
        env_path.write_text(
            "\n".join(
                [
                    f"TARGET_WORKSPACE_PATH={target}",
                    f"PROJECT_WORKSPACE_ID={workspace_name}",
                    f"COMPOSE_PROJECT_NAME=factory_{workspace_name}",
                    f"FACTORY_DIR={factory_dir}",
                    f"FACTORY_DATA_DIR={data_root}",
                    "CONTEXT7_API_KEY=",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        config = factory_workspace.build_runtime_config(
            target,
            factory_dir=factory_dir,
            registry_path=registry_path,
        )
        factory_workspace.sync_runtime_artifacts(config, registry_path=registry_path)
        return target, factory_dir, data_root, config

    def _lookup_record_by_target(
        registry: dict[str, Any],
        target: Path,
    ) -> dict[str, Any]:
        target_str = str(target.resolve())
        for record in registry.get("workspaces", {}).values():
            if not isinstance(record, dict):
                continue
            if str(record.get("target_workspace_path", "")).strip() == target_str:
                return record
        raise AssertionError(f"No registry record found for target {target_str}")

    cleanup_target, cleanup_factory_dir, cleanup_data_root, cleanup_config = (
        _prepare_runtime("cleanup-target")
    )

    factory_stack.cleanup_workspace(
        cleanup_factory_dir,
        env_file=cleanup_factory_dir / ".factory.env",
    )

    assert not (cleanup_target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert not (
        cleanup_target / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    ).exists()
    assert not (
        cleanup_data_root / "memory" / cleanup_config.factory_instance_id
    ).exists()
    assert not (cleanup_data_root / "bus" / cleanup_config.factory_instance_id).exists()

    reg = factory_workspace.load_registry(registry_path)
    cleanup_record = _lookup_record_by_target(reg, cleanup_target)
    assert cleanup_record["runtime_state"] == "runtime-deleted"
    assert cleanup_record["last_runtime_action"] == "cleanup"
    assert cleanup_record["last_runtime_action_reason_codes"] == []

    factory_workspace.save_registry(
        {
            "version": 1,
            "active_workspace": "",
            "workspaces": {},
            "updated_at": factory_workspace.utc_now_iso(),
        },
        registry_path,
    )

    delete_target, delete_factory_dir, delete_data_root, delete_config = (
        _prepare_runtime("delete-target")
    )

    manager = factory_stack.build_runtime_manager()
    manager.delete_runtime(
        delete_factory_dir,
        env_file=delete_factory_dir / ".factory.env",
        reason_codes=("missing-runtime-metadata",),
    )
    output = capsys.readouterr().out

    assert not (delete_target / ".copilot/softwareFactoryVscode/.factory.env").exists()
    assert not (
        delete_target / ".copilot/softwareFactoryVscode/.tmp" / "runtime-manifest.json"
    ).exists()
    assert not (
        delete_data_root / "memory" / delete_config.factory_instance_id
    ).exists()
    assert not (delete_data_root / "bus" / delete_config.factory_instance_id).exists()

    reg = factory_workspace.load_registry(registry_path)
    delete_record = _lookup_record_by_target(reg, delete_target)

    assert delete_record["runtime_state"] == "runtime-deleted"
    assert delete_record["last_runtime_action"] == "delete-runtime"
    assert delete_record["last_runtime_action_reason_codes"] == [
        "missing-runtime-metadata"
    ]
    assert (
        "`delete-runtime` removed workspace containers and named volumes when present"
        in output
    )
    assert "Docker images were retained" in output


def test_cleanup_workspace_still_cleans_contract_when_runtime_sync_fails(
    tmp_path: Path, monkeypatch
):
    target = tmp_path / "target"
    target.mkdir(parents=True, exist_ok=True)
    factory_dir = target / ".copilot/softwareFactoryVscode"
    factory_dir.mkdir(parents=True, exist_ok=True)
    env_path = factory_dir / ".factory.env"
    env_path.write_text("CONTEXT7_API_KEY=\n", encoding="utf-8")
    manifest_path = target / ".copilot/softwareFactoryVscode/.tmp/runtime-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("{}\n", encoding="utf-8")

    def _raise_sync_failure(*_args, **_kwargs):
        raise RuntimeError("simulated runtime sync failure")

    monkeypatch.setattr(factory_stack, "sync_workspace_runtime", _raise_sync_failure)

    exit_code = factory_stack.cleanup_workspace(factory_dir, env_file=env_path)

    assert exit_code == 0
    assert not env_path.exists()
    assert not manifest_path.exists()


def test_resolve_env_file_prefers_companion_namespaced_env_for_source_checkout(
    tmp_path: Path,
):
    source_repo = tmp_path / "work" / "softwareFactoryVscode"
    source_repo.mkdir(parents=True, exist_ok=True)
    companion_env = tmp_path / ".copilot" / "softwareFactoryVscode" / ".factory.env"
    companion_env.parent.mkdir(parents=True, exist_ok=True)
    companion_env.write_text("TARGET_WORKSPACE_PATH=/tmp/demo\n", encoding="utf-8")

    resolved = factory_stack.resolve_env_file(source_repo)

    assert resolved == companion_env.resolve()


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

    factory_stack.status_workspace(
        repo_root, env_file=target_repo / ".copilot/softwareFactoryVscode/.factory.env"
    )
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


def test_workspace_sensitive_tasks_use_surface_guard() -> None:
    tasks_path = REPO_ROOT / ".vscode" / "tasks.json"
    tasks_data = json.loads(tasks_path.read_text(encoding="utf-8"))
    tasks = {
        task["label"]: task
        for task in tasks_data.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("label"), str)
    }

    expected_operations = {
        "🛂 Verify: Installation Compliance": "verify-install",
        "🩺 Verify: Runtime Compliance": "verify-runtime",
        "🩺 Verify: Runtime Compliance + MCP": "verify-runtime-mcp",
        "🔎 Check: Factory Updates": "update-check",
        "⬆️ Update: Factory Install": "update-apply",
    }

    for label, operation in expected_operations.items():
        task = tasks[label]
        assert (
            task["args"][0] == "${workspaceFolder}/scripts/workspace_surface_guard.py"
        )
        assert task["args"][1] == operation
        assert task["args"][2] == "--target"
        assert task["args"][3] == "${workspaceFolder:Host Project (Root)}"

    preflight_task = tasks["🧭 Runtime: Preflight"]
    assert preflight_task["args"] == [
        "${workspaceFolder}/scripts/factory_stack.py",
        "preflight",
    ]
