import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest


def _load_recovery_module():
    repo_root = Path(__file__).parent.parent
    module_path = repo_root / "scripts" / "capture_recovery_snapshot.py"
    spec = importlib.util.spec_from_file_location(
        "capture_recovery_snapshot_module", module_path
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _completed(command, stdout, *, returncode=0, stderr=""):
    return subprocess.CompletedProcess(
        list(command),
        returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_resolve_output_path_rejects_paths_outside_repo_tmp(tmp_path):
    module = _load_recovery_module()
    repo_root = tmp_path / "repo"
    (repo_root / ".tmp").mkdir(parents=True)

    with pytest.raises(ValueError):
        module.resolve_output_path(repo_root, repo_root / "snapshot.md")


def test_capture_recovery_snapshot_writes_required_sections(tmp_path):
    module = _load_recovery_module()
    repo_root = tmp_path / "repo"
    tmp_dir = repo_root / ".tmp"
    tmp_dir.mkdir(parents=True)
    checkpoint_path = tmp_dir / "github-issue-queue-state.md"
    checkpoint_path.write_text(
        "\n".join(
            [
                "# GitHub issue queue state",
                "",
                "- active_issue: 63",
                "- active_branch: issue-63-interruption-recovery",
                "- active_pr: 77",
                "- status: implementing",
                "- last_validation: none",
                "- next_gate: capture a deterministic recovery snapshot",
                "- blocker: none",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_path = tmp_dir / "interruption-recovery-snapshot.md"

    def fake_runner(command, cwd):
        del cwd
        command = list(command)
        if command[:4] == ["git", "rev-parse", "--abbrev-ref", "HEAD"]:
            return _completed(command, "issue-63-interruption-recovery\n")
        if command[:3] == ["git", "status", "--short"]:
            return _completed(command, "## issue-63-interruption-recovery\n")
        if command[:3] == ["gh", "issue", "view"]:
            return _completed(
                command,
                '{"state":"OPEN","url":"https://github.com/blecx/softwareFactoryVscode/issues/63",'
                '"title":"Issue 63","closedAt":null}\n',
            )
        if command[:3] == ["gh", "pr", "view"]:
            return _completed(
                command,
                '{"state":"OPEN","isDraft":false,"mergeable":"MERGEABLE",'
                '"url":"https://github.com/blecx/softwareFactoryVscode/pull/77",'
                '"mergedAt":null}\n',
            )
        if command[:3] == ["gh", "pr", "checks"]:
            return _completed(command, "Python Code Quality (Lint & Format)\tpass\n")
        if "factory_stack.py" in " ".join(command):
            return _completed(
                command,
                "runtime_state=running\npreflight_status=ready\n",
            )
        raise AssertionError(f"Unexpected command: {command}")

    module.capture_recovery_snapshot(
        repo_root=repo_root,
        checkpoint_path=checkpoint_path,
        output_path=output_path,
        include_runtime_status=True,
        runner=fake_runner,
        generated_at="2026-04-19T20:40:00Z",
    )

    snapshot = output_path.read_text(encoding="utf-8")
    assert "# Interruption recovery snapshot" in snapshot
    assert "- generated_at: 2026-04-19T20:40:00Z" in snapshot
    assert "## Queue checkpoint" in snapshot
    assert "- active_issue: 63" in snapshot
    assert "## Local git state" in snapshot
    assert "## GitHub truth" in snapshot
    assert "Issue #63 GitHub truth" in snapshot
    assert "PR #77 check state" in snapshot
    assert "## Runtime / service snapshot" in snapshot
    assert "factory_stack runtime status" in snapshot
    assert "## Next resume checklist" in snapshot
