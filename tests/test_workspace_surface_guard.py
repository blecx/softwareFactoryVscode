from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import workspace_surface_guard


def create_host_surface(target_dir: Path) -> Path:
    metadata_dir = target_dir / ".copilot" / "softwareFactoryVscode"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / ".factory.env").write_text(
        f"TARGET_WORKSPACE_PATH={target_dir}\n",
        encoding="utf-8",
    )
    (metadata_dir / "lock.json").write_text("{}\n", encoding="utf-8")
    (target_dir / workspace_surface_guard.DEFAULT_WORKSPACE_FILENAME).write_text(
        "{}\n",
        encoding="utf-8",
    )
    return target_dir


def test_resolve_operation_target_accepts_generated_workspace_target(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "work" / "softwareFactoryVscode"
    repo_root.mkdir(parents=True)
    target_dir = create_host_surface(tmp_path / "host")

    resolved = workspace_surface_guard.resolve_operation_target(
        repo_root,
        str(target_dir),
        workspace_surface_guard.DEFAULT_WORKSPACE_FILENAME,
        workspace_surface_guard.OPERATIONS["verify-runtime"],
    )

    assert resolved == target_dir.resolve()


def test_resolve_operation_target_rejects_source_checkout_with_guidance(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "work" / "softwareFactoryVscode"
    repo_root.mkdir(parents=True)
    companion_target = create_host_surface(tmp_path)

    with pytest.raises(workspace_surface_guard.SurfaceRoutingError) as excinfo:
        workspace_surface_guard.resolve_operation_target(
            repo_root,
            workspace_surface_guard.HOST_PROJECT_ROOT_PLACEHOLDER,
            workspace_surface_guard.DEFAULT_WORKSPACE_FILENAME,
            workspace_surface_guard.OPERATIONS["verify-install"],
        )

    message = str(excinfo.value)
    assert "source checkout" in message
    assert "generated workspace" in message
    assert "companion runtime" in message
    assert (
        str(companion_target / workspace_surface_guard.DEFAULT_WORKSPACE_FILENAME)
        in message
    )


def test_main_runs_wrapped_command_for_valid_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "work" / "softwareFactoryVscode"
    (repo_root / "scripts").mkdir(parents=True)
    target_dir = create_host_surface(tmp_path / "host")
    observed: dict[str, object] = {}

    def fake_run(command: list[str], check: bool, text: bool) -> SimpleNamespace:
        observed["command"] = command
        observed["check"] = check
        observed["text"] = text
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(workspace_surface_guard.subprocess, "run", fake_run)

    exit_code = workspace_surface_guard.main(
        [
            "verify-runtime-mcp",
            "--repo-root",
            str(repo_root),
            "--target",
            str(target_dir),
        ]
    )

    assert exit_code == 0
    assert observed["check"] is False
    assert observed["text"] is True
    assert observed["command"] == [
        sys.executable,
        str(repo_root / "scripts" / "verify_factory_install.py"),
        "--runtime",
        "--check-vscode-mcp",
        "--target",
        str(target_dir.resolve()),
    ]
