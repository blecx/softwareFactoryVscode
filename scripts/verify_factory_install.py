#!/usr/bin/env python3
"""Verify that a Software Factory installation complies with the host contract."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from http.client import RemoteDisconnected
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import bootstrap_host
import factory_stack
import factory_workspace

DEFAULT_WORKSPACE_FILENAME = "software-factory.code-workspace"
DEFAULT_RUNTIME_TIMEOUT = 2.0
REQUIRED_FACTORY_FILES = [
    Path("scripts") / "bootstrap_host.py",
    Path("scripts") / "factory_release.py",
    Path("scripts") / "factory_update.py",
    Path("scripts") / "install_factory.py",
    Path("scripts") / "verify_factory_install.py",
]
BASH_GATEWAY_POLICY_PATH = Path("configs") / "bash_gateway_policy.default.yml"
BASH_GATEWAY_SETTINGS_PATH = Path(".copilot") / "config" / "vscode-agent-settings.json"
REQUIRED_WORKSPACE_FOLDERS = [
    ("Host Project (Root)", "."),
    ("AI Agent Factory", bootstrap_host.FACTORY_DIRNAME),
]
RUNTIME_SERVICES = factory_workspace.RUNTIME_SERVICE_CONTRACT


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a target repository after Software Factory installation."
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target repository root (default: current directory)",
    )
    parser.add_argument(
        "--workspace-file",
        default=DEFAULT_WORKSPACE_FILENAME,
        help=(
            "Workspace filename to verify in the target repository "
            f"(default: {DEFAULT_WORKSPACE_FILENAME})"
        ),
    )
    parser.add_argument(
        "--skip-workspace-check",
        action="store_true",
        help="Skip verification of the generated workspace file.",
    )
    parser.add_argument(
        "--skip-gitignore-check",
        action="store_true",
        help="Skip verification of the target repository .gitignore entries.",
    )
    parser.add_argument(
        "--no-smoke-prompt",
        action="store_true",
        help="Suppress printing the non-mutating VS Code smoke prompt on success.",
    )
    parser.add_argument(
        "--runtime",
        action="store_true",
        help="Also verify the core runtime stack after services have been started.",
    )
    parser.add_argument(
        "--check-vscode-mcp",
        action="store_true",
        help="With --runtime, also verify the VS Code MCP localhost endpoints are reachable.",
    )
    parser.add_argument(
        "--runtime-timeout",
        type=float,
        default=DEFAULT_RUNTIME_TIMEOUT,
        help=f"HTTP runtime probe timeout in seconds (default: {DEFAULT_RUNTIME_TIMEOUT})",
    )
    return parser.parse_args(argv)


def parse_env_file(path: Path) -> dict[str, str]:
    return factory_workspace.parse_env_file(path)


def load_runtime_manifest(target_dir: Path) -> dict[str, Any]:
    manifest_path = (
        target_dir
        / factory_workspace.TMP_SUBPATH
        / factory_workspace.RUNTIME_MANIFEST_FILENAME
    )
    return factory_workspace.load_json(manifest_path)


def render_smoke_prompt(target_dir: Path, workspace_file: str) -> str:
    return "\n".join(
        [
            "Please perform a read-only smoke test for this installed Software Factory workspace.",
            f"Target repository: `{target_dir}`",
            f"Open/use workspace file: `{workspace_file}`",
            "",
            "Rules:",
            "1. Do not create, modify, delete, stage, commit, or rename any file.",
            "2. Do not run docker, git, or terminal commands that change state.",
            "3. If you need shell commands, use read-only inspection commands only.",
            "4. Treat `.factory.env` as sensitive and redact secrets if you mention it.",
            "",
            "Please verify and report PASS/FAIL with evidence for:",
            "- The workspace shows both the host project root and `.copilot/softwareFactoryVscode`.",
            "- `.copilot/softwareFactoryVscode/lock.json`, `.factory.env`, and the workspace file exist.",
            "- `.copilot/softwareFactoryVscode/scripts/verify_factory_install.py` appears present.",
            "- The installation looks compliant with namespace-first and ready for VS Code usage.",
            "",
            "Do not make any edits; only inspect and summarize.",
        ]
    )


def render_runtime_smoke_prompt(target_dir: Path, workspace_file: str) -> str:
    return "\n".join(
        [
            "Please perform a read-only runtime smoke test for this Software Factory installation.",
            f"Target repository: `{target_dir}`",
            f"Workspace file: `{workspace_file}`",
            "",
            "Rules:",
            "1. Do not modify files, environment variables, docker configuration, or git state.",
            "2. Do not start, stop, rebuild, or restart containers during this smoke test.",
            "3. Use read-only inspection only and report observable evidence.",
            "",
            "Please verify and report PASS/FAIL with evidence for:",
            "- The core compose services are running and healthy where health checks exist.",
            "- The generated runtime manifest and effective workspace settings agree on the active endpoint map.",
            "- The effective health endpoints respond for this workspace's assigned ports.",
            "- If MCP endpoints are part of this runtime, confirm whether the "
            "generated workspace MCP URLs appear reachable.",
            "",
            "Do not make any edits; only inspect and summarize.",
        ]
    )


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    capture_output: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        check=True,
        text=True,
        capture_output=capture_output,
    )


def probe_http_url(
    url: str,
    *,
    timeout: float,
    allow_http_error: bool,
) -> str | None:
    try:
        with urlopen(url, timeout=timeout):
            return None
    except RemoteDisconnected:
        if allow_http_error:
            return None
        return f"HTTP probe failed for {url}: remote disconnected before response"
    except HTTPError as exc:
        if allow_http_error:
            return None
        return f"HTTP probe failed for {url}: HTTP {exc.code}"
    except URLError as exc:
        return f"HTTP probe failed for {url}: {exc.reason}"


def collect_running_services(compose_project_name: str) -> dict[str, str]:
    format_string = '{{.Label "com.docker.compose.service"}}|{{.Status}}'
    result = run_command(
        [
            "docker",
            "ps",
            "--filter",
            f"label=com.docker.compose.project={compose_project_name}",
            "--format",
            format_string,
        ],
        capture_output=True,
    )
    services: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if not line.strip() or "|" not in line:
            continue
        service, status = line.split("|", 1)
        services[service.strip()] = status.strip()
    return services


def load_vscode_mcp_server_urls(
    target_dir: Path, workspace_file: str
) -> dict[str, str]:
    workspace_path = target_dir / workspace_file
    config_data = (
        bootstrap_host.load_json(workspace_path) if workspace_path.exists() else {}
    )
    servers = config_data.get("settings", {}).get("mcp", {}).get("servers", {})
    if not isinstance(servers, dict) or not servers:
        config_path = (
            target_dir
            / bootstrap_host.FACTORY_DIRNAME
            / ".copilot"
            / "config"
            / "vscode-agent-settings.json"
        )
        config_data = bootstrap_host.load_json(config_path)
        servers = config_data.get("workspace", {}).get("mcp", {}).get("servers", {})
    urls: dict[str, str] = {}
    if not isinstance(servers, dict):
        return urls
    for name, data in servers.items():
        if isinstance(data, dict) and isinstance(data.get("url"), str):
            urls[name] = data["url"]
    return urls


def check_factory_tree(target_dir: Path, violations: list[str]) -> Path | None:
    factory_dir = target_dir / bootstrap_host.FACTORY_DIRNAME
    if not factory_dir.is_dir():
        violations.append(f"Missing factory directory: {factory_dir}")
        return None

    if not (factory_dir / ".git").exists():
        violations.append(f"Factory directory is not a git checkout: {factory_dir}")

    for relative_path in REQUIRED_FACTORY_FILES:
        candidate = factory_dir / relative_path
        if not candidate.exists():
            violations.append(f"Missing required factory file: {candidate}")

    return factory_dir


def check_bash_gateway_configuration(target_dir: Path, violations: list[str]) -> None:
    factory_dir = target_dir / bootstrap_host.FACTORY_DIRNAME

    settings_path = factory_dir / BASH_GATEWAY_SETTINGS_PATH
    if not settings_path.exists():
        violations.append(
            f"Missing VS Code MCP settings file for bash gateway: {settings_path}"
        )
    else:
        try:
            settings = bootstrap_host.load_json(settings_path)
        except Exception as exc:
            violations.append(
                f"Unable to parse VS Code MCP settings JSON at {settings_path}: {exc}"
            )
        else:
            bash_url = (
                settings.get("workspace", {})
                .get("mcp", {})
                .get("servers", {})
                .get("bashGateway", {})
                .get("url")
            )
            if not isinstance(bash_url, str) or not bash_url:
                violations.append(
                    "VS Code MCP settings are missing `workspace.mcp.servers.bashGateway.url`."
                )

    policy_path = factory_dir / BASH_GATEWAY_POLICY_PATH
    if not policy_path.exists():
        violations.append(f"Missing bash gateway policy file: {policy_path}")
        return

    try:
        policy_data = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        violations.append(
            f"Unable to parse bash gateway policy YAML at {policy_path}: {exc}"
        )
        return

    profiles = policy_data.get("profiles") if isinstance(policy_data, dict) else None
    if not isinstance(profiles, dict) or not profiles:
        violations.append(
            "Bash gateway policy must define a non-empty top-level `profiles` mapping."
        )
        return

    for profile_name, profile_data in profiles.items():
        if not isinstance(profile_data, dict):
            violations.append(
                f"Bash gateway profile `{profile_name}` must be a mapping of settings."
            )
            continue
        scripts = profile_data.get("scripts")
        if not isinstance(scripts, list) or not all(
            isinstance(item, str) and item for item in scripts
        ):
            violations.append(
                f"Bash gateway profile `{profile_name}` must define a non-empty string list for `scripts`."
            )


def check_factory_env(target_dir: Path, violations: list[str]) -> None:
    env_path = target_dir / bootstrap_host.FACTORY_DIRNAME / ".factory.env"
    if not env_path.exists():
        violations.append(f"Missing environment contract: {env_path}")
        return

    values = parse_env_file(env_path)
    runtime_manifest = load_runtime_manifest(target_dir)
    expected_workspace = str(target_dir)
    if values.get("TARGET_WORKSPACE_PATH") != expected_workspace:
        violations.append(
            "TARGET_WORKSPACE_PATH does not match the target repository "
            f"(expected `{expected_workspace}`, found `{values.get('TARGET_WORKSPACE_PATH', '')}`)."
        )

    project_id = values.get("PROJECT_WORKSPACE_ID", "")
    if not project_id:
        violations.append("PROJECT_WORKSPACE_ID is missing or empty in .factory.env")

    compose_name = values.get("COMPOSE_PROJECT_NAME", "")
    if not compose_name:
        violations.append("COMPOSE_PROJECT_NAME is missing or empty in .factory.env")
    elif not compose_name.startswith("factory_"):
        violations.append(
            f"COMPOSE_PROJECT_NAME should start with `factory_` (found `{compose_name}`)."
        )

    if "CONTEXT7_API_KEY" not in values:
        violations.append("CONTEXT7_API_KEY entry is missing in .factory.env")

    instance_id = values.get("FACTORY_INSTANCE_ID", "")
    if runtime_manifest:
        if instance_id and runtime_manifest.get("factory_instance_id") != instance_id:
            violations.append(
                "FACTORY_INSTANCE_ID in .factory.env does not match the generated runtime manifest."
            )

        expected_factory_dir = str(target_dir / bootstrap_host.FACTORY_DIRNAME)
        actual_factory_dir = values.get("FACTORY_DIR", "")
        if actual_factory_dir and actual_factory_dir != expected_factory_dir:
            violations.append(
                "FACTORY_DIR does not match the installed harness namespace factory path "
                f"(expected `{expected_factory_dir}`, found `{actual_factory_dir}`)."
            )


def check_lock_file(
    target_dir: Path, workspace_file: str, violations: list[str]
) -> None:
    lock_path = target_dir / ".copilot/softwareFactoryVscode/lock.json"
    if not lock_path.exists():
        violations.append(f"Missing installation metadata lock file: {lock_path}")
        return

    lock_data = bootstrap_host.load_json(lock_path)
    if not lock_data.get("version"):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json is missing `version`"
        )
    if not lock_data.get("installed_at"):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json is missing `installed_at`"
        )
    if not lock_data.get("updated_at"):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json is missing `updated_at`"
        )

    factory_data = lock_data.get("factory")
    if not isinstance(factory_data, dict):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json is missing `factory` metadata"
        )
        return

    if factory_data.get("install_path") != bootstrap_host.FACTORY_DIRNAME:
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json `factory.install_path` "
            "does not match the harness namespace install path"
        )
    if factory_data.get("workspace_file") != workspace_file:
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json `factory.workspace_file` "
            "does not match the expected workspace filename"
        )
    if not factory_data.get("repo_url"):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json `factory.repo_url` is missing"
        )
    if not factory_data.get("commit"):
        violations.append(
            ".copilot/softwareFactoryVscode/lock.json `factory.commit` is missing"
        )

    release_data = lock_data.get("release")
    if isinstance(release_data, dict):
        if not release_data.get("display_version"):
            violations.append(
                ".copilot/softwareFactoryVscode/lock.json `release.display_version` is missing"
            )
        if not release_data.get("commit_sha"):
            violations.append(
                ".copilot/softwareFactoryVscode/lock.json `release.commit_sha` is missing"
            )
        if not release_data.get("manifest_path"):
            violations.append(
                ".copilot/softwareFactoryVscode/lock.json `release.manifest_path` is missing"
            )


def check_workspace_file(
    target_dir: Path,
    workspace_file: str,
    *,
    skip_workspace_check: bool,
    violations: list[str],
) -> None:
    if skip_workspace_check:
        return

    workspace_path = target_dir / workspace_file
    if not workspace_path.exists():
        violations.append(f"Missing host-facing workspace file: {workspace_path}")
        return

    workspace_data = bootstrap_host.load_json(workspace_path)
    folders = workspace_data.get("folders")
    if not isinstance(folders, list):
        violations.append(
            f"Workspace file does not contain a valid `folders` array: {workspace_path}"
        )
        return

    actual_folders = [
        (entry.get("name"), entry.get("path"))
        for entry in folders
        if isinstance(entry, dict)
    ]
    for expected in REQUIRED_WORKSPACE_FOLDERS:
        if expected not in actual_folders:
            violations.append(
                "Workspace file is missing required folder mapping "
                f"`name={expected[0]}`, `path={expected[1]}`"
            )


def check_gitignore(
    target_dir: Path,
    *,
    skip_gitignore_check: bool,
    violations: list[str],
) -> None:
    if skip_gitignore_check:
        return

    gitignore_path = target_dir / ".gitignore"
    if not gitignore_path.exists():
        violations.append(f"Missing .gitignore file: {gitignore_path}")
        return

    lines = gitignore_path.read_text(encoding="utf-8").splitlines()
    missing = [entry for entry in bootstrap_host.GITIGNORE_BLOCK if entry not in lines]
    for entry in missing:
        violations.append(
            f".gitignore is missing required factory ignore entry: {entry}"
        )

    legacy_entries = bootstrap_host.find_legacy_gitignore_entries(lines)
    for entry in legacy_entries:
        violations.append(
            ".gitignore still contains a legacy hidden-tree Software Factory entry: "
            f"{entry}"
        )


def check_for_legacy_mode(target_dir: Path) -> None:
    legacy_dir = target_dir / ".softwareFactoryVscode"
    if legacy_dir.exists() and legacy_dir.is_dir():
        print(
            "⚠️  WARNING: Repository is operating in transitional/legacy mode (.softwareFactoryVscode detected)."
        )
        print(
            "    Please migrate to the namespace-first architecture (.copilot/softwareFactoryVscode) structure."
        )


def check_legacy_install_artifacts(target_dir: Path, violations: list[str]) -> None:
    legacy_paths = [
        target_dir / ".softwareFactoryVscode",
        target_dir / ".tmp" / "softwareFactoryVscode",
        target_dir / ".factory.env",
        target_dir / ".factory.lock.json",
    ]

    for legacy_path in legacy_paths:
        if legacy_path.exists():
            violations.append(
                "Legacy installation artifact is still present and should have been removed during upgrade: "
                f"{legacy_path}"
            )


def verify_installation(
    target_dir: Path,
    *,
    workspace_file: str,
    skip_workspace_check: bool,
    skip_gitignore_check: bool,
) -> list[str]:

    check_for_legacy_mode(target_dir)
    violations: list[str] = []
    check_legacy_install_artifacts(target_dir, violations)
    check_factory_tree(target_dir, violations)
    check_bash_gateway_configuration(target_dir, violations)
    check_factory_env(target_dir, violations)
    check_lock_file(target_dir, workspace_file, violations)
    check_workspace_file(
        target_dir,
        workspace_file,
        skip_workspace_check=skip_workspace_check,
        violations=violations,
    )
    check_gitignore(
        target_dir,
        skip_gitignore_check=skip_gitignore_check,
        violations=violations,
    )
    return violations


def verify_runtime(
    target_dir: Path,
    *,
    workspace_file: str,
    timeout: float,
    check_vscode_mcp: bool,
) -> list[str]:

    check_for_legacy_mode(target_dir)
    violations: list[str] = []

    if shutil.which("docker") is None:
        return [
            "Docker CLI is not available on PATH, so runtime compliance cannot be verified."
        ]

    env_path = target_dir / bootstrap_host.FACTORY_DIRNAME / ".factory.env"
    if not env_path.exists():
        return [
            f"Missing environment contract required for runtime verification: {env_path}"
        ]

    env_values = parse_env_file(env_path)
    factory_dir = target_dir / bootstrap_host.FACTORY_DIRNAME
    preflight = factory_stack.build_preflight_report(
        factory_dir,
        env_file=env_path,
        workspace_file=workspace_file,
    )
    if preflight["status"] != "ready":
        return [str(issue) for issue in preflight["issues"]]

    runtime_manifest = load_runtime_manifest(target_dir)
    compose_project_name = str(
        runtime_manifest.get("compose_project_name")
        or env_values.get("COMPOSE_PROJECT_NAME", "")
    )
    if not compose_project_name:
        return ["COMPOSE_PROJECT_NAME is missing or empty in .factory.env"]

    ports = factory_workspace.build_port_values(0)
    manifest_ports = runtime_manifest.get("ports", {})
    if isinstance(manifest_ports, dict):
        for key, value in manifest_ports.items():
            if key in ports:
                try:
                    ports[key] = int(value)
                except (TypeError, ValueError):
                    continue
    for key in ports:
        raw_value = env_values.get(key, "").strip()
        if not raw_value:
            continue
        try:
            ports[key] = int(raw_value)
        except ValueError:
            continue

    running_services = {
        service_name: str(data.get("status", ""))
        for service_name, data in preflight["service_inventory"].items()
    }

    for service_name, metadata in RUNTIME_SERVICES.items():
        status = running_services.get(service_name)
        if not status:
            violations.append(
                "Required runtime service "
                f"`{service_name}` is not running for compose project "
                f"`{compose_project_name}`."
            )
            continue

        if metadata["require_healthy_status"] and "healthy" not in status.lower():
            violations.append(
                f"Runtime service `{service_name}` is not healthy (docker status: `{status}`)."
            )
        elif "up" not in status.lower():
            violations.append(
                f"Runtime service `{service_name}` is not reported as running (docker status: `{status}`)."
            )

        port_key = metadata["port_key"]
        health_path = metadata["health_path"]
        if port_key and health_path:
            health_url = f"http://127.0.0.1:{ports[port_key]}{health_path}"
            error = probe_http_url(
                health_url,
                timeout=timeout,
                allow_http_error=bool(metadata.get("allow_http_error", False)),
            )
            if error:
                violations.append(error)

    if check_vscode_mcp:
        server_urls = preflight["workspace_urls"] or load_vscode_mcp_server_urls(
            target_dir, workspace_file
        )
        if not server_urls:
            violations.append(
                "Could not load VS Code MCP server URLs from "
                "the generated workspace file or canonical VS Code MCP config."
            )
        for server_name, url in server_urls.items():
            if not url.startswith("http://127.0.0.1") and not url.startswith(
                "http://localhost"
            ):
                continue
            error = probe_http_url(url, timeout=timeout, allow_http_error=True)
            if error:
                violations.append(
                    "VS Code MCP endpoint "
                    f"`{server_name}` is not reachable at {url}: {error}"
                )

    return violations


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir = bootstrap_host.resolve_target_dir(args.target)

    print("=================================================")
    print("🔎 Verifying Software Factory Installation")
    print("=================================================")
    print(f"Target Project: {target_dir}")

    violations = verify_installation(
        target_dir,
        workspace_file=args.workspace_file,
        skip_workspace_check=args.skip_workspace_check,
        skip_gitignore_check=args.skip_gitignore_check,
    )
    if violations:
        print("❌ Installation compliance failed:")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print("✅ Installation compliance passed.")
    print(
        "The harness namespace install, host contract, and canonical workspace entrypoint look correct."
    )

    runtime_violations: list[str] = []
    if args.runtime:
        print("\n🔁 Verifying runtime compliance...")
        runtime_violations = verify_runtime(
            target_dir,
            workspace_file=args.workspace_file,
            timeout=args.runtime_timeout,
            check_vscode_mcp=args.check_vscode_mcp,
        )
        if runtime_violations:
            print("❌ Runtime compliance failed:")
            for violation in runtime_violations:
                print(f"  - {violation}")
            return 1
        print("✅ Runtime compliance passed.")
        print(
            "The core compose services and requested runtime endpoints are reachable."
        )

    if not args.no_smoke_prompt:
        print(
            "\n🧪 Non-mutating VS Code smoke prompt (copy into Copilot Chat if desired):\n"
        )
        print(render_smoke_prompt(target_dir, args.workspace_file))
        if args.runtime:
            print("\n🧪 Non-mutating runtime smoke prompt:\n")
            print(render_runtime_smoke_prompt(target_dir, args.workspace_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
