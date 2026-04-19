import importlib.util
import sys
from pathlib import Path


def _load_guard_module():
    repo_root = Path(__file__).parent.parent
    module_path = repo_root / "scripts" / "github_issue_queue_guard.py"
    spec = importlib.util.spec_from_file_location(
        "github_issue_queue_guard_module", module_path
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write_state(state_path: Path, **overrides) -> None:
    state = {
        "active_issue": "62",
        "active_branch": "issue-62-github-truth-enforcement",
        "active_pr": "101",
        "status": "ready-for-pr-merge",
        "last_validation": "./.venv/bin/python ./scripts/local_ci_parity.py",
        "next_gate": "merge via pr-merge",
        "blocker": "none",
        "issue_state": "open-verified-on-github",
        "pr_state": "open-and-mergeable",
        "ci_state": "passed",
        "cleanup_state": "pending-post-merge",
        "last_github_truth": "gh issue view 62 && gh pr checks 101",
    }
    state.update(overrides)
    lines = ["# GitHub issue queue state", ""]
    lines.extend(f"- {key}: {value}" for key, value in state.items())
    state_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_guard_blocks_merge_without_checkpoint(tmp_path):
    module = _load_guard_module()

    result = module.evaluate_prompt("merge the pr", state_path=tmp_path / "missing.md")

    assert result["continue"] is False
    assert result["stopReason"] == "Missing ordered-issue checkpoint"
    assert "docs/WORK-ISSUE-WORKFLOW.md" in result["systemMessage"]


def test_guard_allows_merge_with_verified_merge_ready_checkpoint(tmp_path):
    module = _load_guard_module()
    state_path = tmp_path / "queue-state.md"
    _write_state(state_path)

    result = module.evaluate_prompt("merge the pr", state_path=state_path)

    assert result == {"continue": True}


def test_guard_blocks_completion_without_merged_github_truth(tmp_path):
    module = _load_guard_module()
    state_path = tmp_path / "queue-state.md"
    _write_state(state_path)

    result = module.evaluate_prompt("close the issue", state_path=state_path)

    assert result["continue"] is False
    assert result["stopReason"] == "Unsafe completion state"
    assert "merged-and-closed" in result["systemMessage"]


def test_guard_allows_completion_after_merged_and_closed_checkpoint(tmp_path):
    module = _load_guard_module()
    state_path = tmp_path / "queue-state.md"
    _write_state(
        state_path,
        status="merged-and-closed",
        issue_state="closed-verified-on-github",
        pr_state="merged-verified-on-github",
        cleanup_state="clean-verified",
    )

    result = module.evaluate_prompt("mark the issue complete", state_path=state_path)

    assert result == {"continue": True}
