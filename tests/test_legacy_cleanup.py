import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.test_factory_install import create_source_factory_repo, init_git_repo, install_factory


def test_install_factory_removes_legacy_structure_after_spinning_down(tmp_path: Path):
    target_dir = tmp_path / "mock-repo"
    target_dir.mkdir()

    # Create legacy `.softwareFactoryVscode` and `.tmp/softwareFactoryVscode`
    legacy_factory = target_dir / ".softwareFactoryVscode"
    legacy_factory.mkdir()
    legacy_tmp = target_dir / ".tmp" / "softwareFactoryVscode"
    legacy_tmp.mkdir(parents=True)
    legacy_env = target_dir / ".factory.env"
    legacy_env.write_text("CONTEXT7_API_KEY=legacy\n", encoding="utf-8")
    legacy_lock = target_dir / ".factory.lock.json"
    legacy_lock.write_text('{"version":"legacy"}\n', encoding="utf-8")

    with patch("subprocess.run") as mock_run:
        # We only want to mock the factory_stack.py stop call during install
        # Let's mock everything in subprocess to avoid actual side effects
        from tests.test_factory_install import git

        git("init", cwd=target_dir)

        # Mock out the rest of the installation
        with patch.object(install_factory, "validate_target_repo"), patch.object(
            install_factory, "clone_factory"
        ), patch.object(
            install_factory, "update_factory", return_value="v1.0"
        ), patch.object(
            install_factory, "head_commit", return_value="abcdef"
        ), patch.object(
            install_factory, "run_command"
        ), patch.object(
            install_factory, "invoke_bootstrap"
        ):

            install_factory.main(["--target", str(target_dir)])

        # Check if subprocess.run was called to stop the legacy stack
        stop_called = False
        for call in mock_run.call_args_list:
            args, kwargs = call
            cmd = args[0]
            if "factory_stack.py" in str(cmd) and "stop" in cmd:
                stop_called = True
                break

        assert stop_called, "Should have stopped the legacy stack before deletion"
        assert not legacy_factory.exists(), "Legacy factory should be deleted"
        assert not legacy_tmp.exists(), "Legacy tmp should be deleted"
        assert not legacy_env.exists(), "Legacy root env file should be deleted"
        assert not legacy_lock.exists(), "Legacy root lock file should be deleted"


def test_install_factory_removes_legacy_root_contract_even_if_miscreated_as_directories(
    tmp_path: Path,
):
    source_repo = tmp_path / "source-factory"
    target_dir = tmp_path / "target-project"
    create_source_factory_repo(source_repo)
    init_git_repo(target_dir)

    legacy_env_dir = target_dir / ".factory.env"
    legacy_env_dir.mkdir(parents=True)
    legacy_lock_dir = target_dir / ".factory.lock.json"
    legacy_lock_dir.mkdir(parents=True)

    exit_code = install_factory.main(
        ["--target", str(target_dir), "--repo-url", str(source_repo)]
    )

    assert exit_code == 0
    assert not legacy_env_dir.exists(), "Legacy env directory should be deleted"
    assert not legacy_lock_dir.exists(), "Legacy lock directory should be deleted"


def test_bootstrap_auto_creates_data_directories(tmp_path: Path):
    target_dir = tmp_path / "target-repo"
    target_dir.mkdir()

    from tests.test_factory_install import bootstrap_host

    bootstrap_host.ensure_tmp_dir(target_dir)

    # Assert
    tmp_dir = target_dir / bootstrap_host.TMP_SUBPATH
    assert tmp_dir.exists()

    # Required data dirs must be created
    for sub in [
        "agent-script-runs",
        "mcp-docker-compose",
        "mcp-test-runner",
        "mcp-github-ops",
        "mcp-offline-docs",
    ]:
        assert (tmp_dir / sub).exists(), f"Data dir {sub} was not auto-created"
