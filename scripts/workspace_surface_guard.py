#!/usr/bin/env python3
"""Guard generated-workspace-sensitive tasks against wrong-surface execution."""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import factory_stack
import factory_workspace

SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_FILENAME = factory_workspace.DEFAULT_WORKSPACE_FILENAME
HOST_PROJECT_ROOT_PLACEHOLDER = "${workspaceFolder:Host Project (Root)}"
UNRESOLVED_WORKSPACE_PREFIX = "${workspaceFolder:"


@dataclass(frozen=True)
class RoutedOperation:
    name: str
    script_name: str
    command_args: tuple[str, ...]


OPERATIONS: dict[str, RoutedOperation] = {
    "verify-install": RoutedOperation(
        name="🛂 Verify: Installation Compliance",
        script_name="verify_factory_install.py",
        command_args=(),
    ),
    "verify-runtime": RoutedOperation(
        name="🩺 Verify: Runtime Compliance",
        script_name="verify_factory_install.py",
        command_args=("--runtime",),
    ),
    "verify-runtime-mcp": RoutedOperation(
        name="🩺 Verify: Runtime Compliance + MCP",
        script_name="verify_factory_install.py",
        command_args=("--runtime", "--check-vscode-mcp"),
    ),
    "update-check": RoutedOperation(
        name="🔎 Check: Factory Updates",
        script_name="factory_update.py",
        command_args=("check",),
    ),
    "update-apply": RoutedOperation(
        name="⬆️ Update: Factory Install",
        script_name="factory_update.py",
        command_args=("apply",),
    ),
}


class SurfaceRoutingError(RuntimeError):
    """Raised when a workspace-sensitive task is launched from the wrong surface."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Guard generated-workspace-sensitive Software Factory tasks against "
            "source-checkout execution."
        )
    )
    parser.add_argument("operation", choices=sorted(OPERATIONS))
    parser.add_argument(
        "--repo-root",
        default=str(SCRIPT_REPO_ROOT),
        help="Factory source checkout containing scripts/ and compose/.",
    )
    parser.add_argument(
        "--target",
        default=HOST_PROJECT_ROOT_PLACEHOLDER,
        help=(
            "Host project root. In the generated workspace this should resolve from "
            "`${workspaceFolder:Host Project (Root)}`."
        ),
    )
    parser.add_argument(
        "--workspace-file",
        default=DEFAULT_WORKSPACE_FILENAME,
        help=(
            "Generated workspace filename expected at the host project root "
            f"(default: {DEFAULT_WORKSPACE_FILENAME})."
        ),
    )
    return parser.parse_args(argv)


def is_unresolved_workspace_target(raw_target: str) -> bool:
    normalized = raw_target.strip()
    return (
        not normalized
        or normalized == HOST_PROJECT_ROOT_PLACEHOLDER
        or normalized.startswith(UNRESOLVED_WORKSPACE_PREFIX)
    )


def has_host_runtime_surface(target_dir: Path) -> bool:
    return factory_workspace.has_managed_workspace_contract(target_dir)


def detect_companion_target(repo_root: Path) -> Path | None:
    env_file = factory_stack.resolve_env_file(repo_root)
    if not env_file.exists():
        return None

    target_dir = factory_stack.resolve_target_dir_from_env(repo_root, env_file)
    if not has_host_runtime_surface(target_dir):
        return None
    return target_dir


def format_manual_command(
    repo_root: Path,
    operation: RoutedOperation,
    target_hint: str,
) -> str:
    command = [
        sys.executable,
        str(repo_root / "scripts" / operation.script_name),
        *operation.command_args,
        "--target",
        target_hint,
    ]
    return " ".join(command)


def build_source_checkout_error(
    repo_root: Path,
    operation: RoutedOperation,
    workspace_file: str,
    companion_target: Path | None,
) -> str:
    lines = [
        f"`{operation.name}` does not belong to the source checkout surface.",
        f"Current surface: source checkout `{repo_root}`.",
        (
            "Required surface: generated workspace `software-factory.code-workspace` "
            "with `Host Project (Root)` available, backed by companion runtime "
            "metadata under `.copilot/softwareFactoryVscode/`."
        ),
    ]

    if companion_target is not None:
        lines.extend(
            [
                (
                    "Detected companion runtime: "
                    f"`{companion_target / factory_workspace.FACTORY_DIRNAME}`."
                ),
                (
                    "Next step: open "
                    f"`{companion_target / workspace_file}` and rerun this task from "
                    "the generated workspace."
                ),
                (
                    "Manual fallback: `"
                    f"{format_manual_command(repo_root, operation, str(companion_target))}`"
                ),
            ]
        )
    else:
        lines.extend(
            [
                "Detected companion runtime: none.",
                (
                    "Next step: install or activate a host workspace so the generated "
                    "workspace file and companion runtime metadata exist, then rerun "
                    "this task from that generated workspace."
                ),
                (
                    "Manual fallback after install: `"
                    f"{format_manual_command(repo_root, operation, '<host-project-root>')}`"
                ),
            ]
        )

    return "\n".join(lines)


def build_invalid_target_error(
    repo_root: Path,
    operation: RoutedOperation,
    invalid_target: Path,
    workspace_file: str,
    companion_target: Path | None,
) -> str:
    lines = [
        f"`{operation.name}` requires the generated workspace or companion runtime surface.",
        f"Current surface: explicit target `{invalid_target}` is missing the installed contract.",
        (
            "Required surface: a host project root that contains both the generated "
            f"`{workspace_file}` file and companion runtime metadata under "
            "`.copilot/softwareFactoryVscode/`."
        ),
    ]
    if companion_target is not None:
        lines.append(
            "Detected companion runtime: "
            f"`{companion_target}`. Open `{companion_target / workspace_file}` or rerun `"
            f"{format_manual_command(repo_root, operation, str(companion_target))}`"
        )
    else:
        lines.append(
            "Detected companion runtime: none. Install or activate a host workspace "
            "before rerunning this task."
        )
    return "\n".join(lines)


def resolve_operation_target(
    repo_root: Path,
    raw_target: str,
    workspace_file: str,
    operation: RoutedOperation,
) -> Path:
    companion_target = detect_companion_target(repo_root)
    if is_unresolved_workspace_target(raw_target):
        raise SurfaceRoutingError(
            build_source_checkout_error(
                repo_root,
                operation,
                workspace_file,
                companion_target,
            )
        )

    target_dir = Path(raw_target).expanduser().resolve()
    if has_host_runtime_surface(target_dir):
        return target_dir

    raise SurfaceRoutingError(
        build_invalid_target_error(
            repo_root,
            operation,
            target_dir,
            workspace_file,
            companion_target,
        )
    )


def build_command(
    repo_root: Path,
    operation: RoutedOperation,
    target_dir: Path,
) -> list[str]:
    return [
        sys.executable,
        str(repo_root / "scripts" / operation.script_name),
        *operation.command_args,
        "--target",
        str(target_dir),
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(args.repo_root).expanduser().resolve()
    operation = OPERATIONS[args.operation]

    try:
        target_dir = resolve_operation_target(
            repo_root,
            args.target,
            args.workspace_file,
            operation,
        )
    except SurfaceRoutingError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2

    completed = subprocess.run(
        build_command(repo_root, operation, target_dir),
        check=False,
        text=True,
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
