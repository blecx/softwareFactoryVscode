import importlib.util
import json
import sys
from pathlib import Path

import pytest

from factory_runtime.agents.agent_registry import resolve_agent_spec
from factory_runtime.agents.complexity_scorer import ComplexityScorer
from factory_runtime.agents.coverage_analyzer import (
    CoverageAnalyzer,
    CoverageFile,
    CoverageReport,
)


def test_complexity_scorer_basic():
    scorer = ComplexityScorer()
    body = (
        "This issue introduces a breaking change to the API and missing test coverage."
    )
    files = ["apps/api/test.py", "apps/tui/other.py"]
    score, breakdown = scorer.score(body, files)
    assert breakdown.file_count_score == 0
    assert breakdown.cross_service_score == 1  # api and tui
    assert breakdown.breaking_score > 0
    assert breakdown.test_gap_score > 0
    assert score > 0


def test_agent_registry():
    spec = resolve_agent_spec("autonomous")
    assert spec == "factory_runtime.agents.factory_adapter:FactoryAdapter"


def test_coverage_analyzer():
    analyzer = CoverageAnalyzer(coverage_threshold=80.0, working_directory="/tmp")
    base_data = {
        "file1.py": CoverageFile(
            path="file1.py",
            total_lines=10,
            covered_lines=8,
            missing_lines=2,
            percent_covered=80.0,
        ),
        "file2.py": CoverageFile(
            path="file2.py",
            total_lines=20,
            covered_lines=20,
            missing_lines=0,
            percent_covered=100.0,
        ),
    }
    head_data = {
        "file1.py": CoverageFile(
            path="file1.py",
            total_lines=10,
            covered_lines=7,
            missing_lines=3,
            percent_covered=70.0,
        ),
        "file2.py": CoverageFile(
            path="file2.py",
            total_lines=20,
            covered_lines=20,
            missing_lines=0,
            percent_covered=100.0,
        ),
    }
    before = CoverageReport(total_percent=90.0, files=base_data)
    after = CoverageReport(total_percent=85.0, files=head_data)

    diff = analyzer.analyze_coverage_impact(before, after, ["file1.py"])
    assert "file1.py" in diff.regressions


def test_copilot_queue_agents_exist_without_legacy_continue_aliases():
    repo_root = Path(__file__).parent.parent
    queue_phase_2 = repo_root / ".github" / "agents" / "queue-phase-2.md"
    queue_backend = repo_root / ".github" / "agents" / "queue-backend.md"
    workflow_doc = repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md"

    assert queue_phase_2.exists()
    assert queue_backend.exists()
    assert not (repo_root / ".github" / "agents" / "continue-phase-2.md").exists()
    assert not (repo_root / ".github" / "agents" / "continue-backend.md").exists()
    assert workflow_doc.exists()

    assert "phase-2-queue-workflow" in queue_phase_2.read_text(encoding="utf-8")
    assert "backend-queue-workflow" in queue_backend.read_text(encoding="utf-8")

    workflow_doc_text = workflow_doc.read_text(encoding="utf-8")

    assert "@queue-backend" in workflow_doc_text
    assert "@queue-phase-2" in workflow_doc_text
    assert "@continue-backend" not in workflow_doc_text
    assert "@continue-phase-2" not in workflow_doc_text


def test_low_friction_profile_approves_canonical_queue_agents():
    repo_root = Path(__file__).parent.parent
    approval_profiles = json.loads(
        (repo_root / ".copilot" / "config" / "vscode-approval-profiles.json").read_text(
            encoding="utf-8"
        )
    )

    auto_approve = approval_profiles["low-friction"]["chat.tools.subagent.autoApprove"]
    assert auto_approve["queue-backend"] is True
    assert auto_approve["queue-phase-2"] is True
    assert "continue-backend" not in auto_approve
    assert "continue-phase-2" not in auto_approve


def test_legacy_continue_alias_files_are_removed():
    repo_root = Path(__file__).parent.parent
    for path in [
        repo_root / ".github" / "agents" / "blecs" / "blecs.continue-backend.md",
        repo_root / ".github" / "agents" / "blecs" / "blecs.continue-phase-2.md",
        repo_root / ".copilot" / "skills" / "continue-backend-workflow" / "SKILL.md",
        repo_root / ".copilot" / "skills" / "continue-phase-2-workflow" / "SKILL.md",
    ]:
        assert not path.exists()


def test_tasks_no_longer_invoke_legacy_issue_loop_scripts():
    repo_root = Path(__file__).parent.parent
    tasks = json.loads(
        (repo_root / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    )
    task_map = {task["label"]: task for task in tasks["tasks"]}

    for label in [
        "🔍 Work on Issue (Dry Run)",
        "💬 Work on Issue (Interactive)",
        "🔁 Issue PR Merge Cleanup Loop",
        "🔁 Issue PR Merge Cleanup Loop (#5)",
    ]:
        task = task_map[label]
        serialized = json.dumps(task)
        assert "scripts/work-issue.py" not in serialized
        assert "scripts/issue-pr-merge-cleanup-loop.sh" not in serialized
        assert "WORK-ISSUE-WORKFLOW.md" in serialized


def test_legacy_loop_script_is_deprecated_by_default():
    repo_root = Path(__file__).parent.parent
    text = (repo_root / "scripts" / "issue-pr-merge-cleanup-loop.sh").read_text(
        encoding="utf-8"
    )
    assert "ALLOW_LEGACY_AUTONOMOUS_LOOP" in text
    assert "docs/WORK-ISSUE-WORKFLOW.md" in text


def test_issue_templates_use_live_repo_labels():
    repo_root = Path(__file__).parent.parent
    feature_template = (
        repo_root / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml"
    ).read_text(encoding="utf-8")
    bug_template = (
        repo_root / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml"
    ).read_text(encoding="utf-8")

    assert 'labels: ["enhancement"]' in feature_template
    assert 'labels: ["bug"]' in bug_template


def test_work_issue_workflow_restores_template_and_precheck_guardrails():
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )

    assert ".github/ISSUE_TEMPLATE/feature_request.yml" in workflow_doc
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in workflow_doc
    assert ".github/pull_request_template.md" in workflow_doc
    assert ".github/workflows/ci.yml" in workflow_doc
    assert "./scripts/validate-pr-template.sh" in workflow_doc
    assert "./tests/run-integration-test.sh" in workflow_doc
    assert "ADR-005-Strong-Templating-Enforcement.md" in workflow_doc
    assert "ADR-006-Local-CI-Parity-Prechecks.md" in workflow_doc


def test_new_adrs_capture_template_and_local_ci_contracts():
    repo_root = Path(__file__).parent.parent
    adr_005 = (
        repo_root / "docs" / "architecture" / "ADR-005-Strong-Templating-Enforcement.md"
    ).read_text(encoding="utf-8")
    adr_006 = (
        repo_root / "docs" / "architecture" / "ADR-006-Local-CI-Parity-Prechecks.md"
    ).read_text(encoding="utf-8")

    assert ".github/ISSUE_TEMPLATE/feature_request.yml" in adr_005
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in adr_005
    assert ".github/pull_request_template.md" in adr_005
    assert "queue-backend" in adr_005
    assert "queue-phase-2" in adr_005

    assert ".github/workflows/ci.yml" in adr_006
    assert "./.venv/bin/black --check factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/flake8 factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/pytest tests/" in adr_006
    assert "./tests/run-integration-test.sh" in adr_006
    assert "./scripts/validate-pr-template.sh <pr-body-file>" in adr_006


def test_queue_skills_reference_historical_guardrails():
    repo_root = Path(__file__).parent.parent
    for path in [
        repo_root / ".copilot" / "skills" / "backend-queue-workflow" / "SKILL.md",
        repo_root / ".copilot" / "skills" / "phase-2-queue-workflow" / "SKILL.md",
    ]:
        text = path.read_text(encoding="utf-8")
        assert ".copilot/skills/a2a-communication/SKILL.md" in text
        assert ".github/workflows/ci.yml" in text
        assert ".github/pull_request_template.md" in text
        assert "validate-pr-template.sh" in text
        assert text.count("ADR-005-Strong-Templating-Enforcement.md") == 1
        assert text.count("ADR-006-Local-CI-Parity-Prechecks.md") == 1


def test_workflow_skill_instruction_numbering_is_monotonic():
    repo_root = Path(__file__).parent.parent
    issue_creation = (
        repo_root / ".copilot" / "skills" / "issue-creation-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    resolve_issue = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert (
        "\n5. Add testable acceptance criteria and validation commands."
        in issue_creation
    )
    assert "\n7. Save draft under `.tmp/issue-<number>-draft.md`" in issue_creation

    assert "\n6. Implement minimal code changes in a dedicated branch." in resolve_issue
    assert "\n11. Address CI failures by root cause and re-validate." in resolve_issue


def test_resolve_and_merge_skills_require_local_ci_prechecks():
    repo_root = Path(__file__).parent.parent
    resolve_skill = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    merge_skill = (
        repo_root / ".copilot" / "skills" / "pr-merge-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")

    for text in [resolve_skill, merge_skill]:
        assert ".github/workflows/ci.yml" in text
        assert "./.venv/bin/black --check factory_runtime/ scripts/ tests/" in text
        assert "./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/" in text
        assert "./.venv/bin/flake8 factory_runtime/ scripts/ tests/" in text
        assert "./.venv/bin/pytest tests/" in text
        assert "./tests/run-integration-test.sh" in text
        assert "./scripts/validate-pr-template.sh" in text


def test_issue_creation_and_closure_workflows_use_canonical_templates():
    repo_root = Path(__file__).parent.parent
    issue_creation = (
        repo_root / ".copilot" / "skills" / "issue-creation-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    close_issue = (
        repo_root / ".copilot" / "skills" / "close-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    close_issue_agent = (repo_root / ".github" / "agents" / "close-issue.md").read_text(
        encoding="utf-8"
    )

    assert ".github/ISSUE_TEMPLATE/feature_request.yml" in issue_creation
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in issue_creation
    assert ".github/issue-closing-template.md" in close_issue
    assert ".github/issue-closing-template.md" in close_issue_agent


def test_workflow_doc_links_remote_protection_guide():
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )

    assert "docs/setup-github-repository.md" in workflow_doc


def test_setup_repo_doc_matches_current_ci_checks():
    repo_root = Path(__file__).parent.parent
    setup_doc = (repo_root / "docs" / "setup-github-repository.md").read_text(
        encoding="utf-8"
    )

    assert "Python Code Quality (Lint & Format)" in setup_doc
    assert "Architectural Boundary Tests" in setup_doc
    assert "PR Template Conformance" in setup_doc


def _load_next_pr_module():
    repo_root = Path(__file__).parent.parent
    next_pr_path = repo_root / "scripts" / "next-pr.py"
    spec = importlib.util.spec_from_file_location("next_pr_module", next_pr_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_next_issue_module():
    repo_root = Path(__file__).parent.parent
    next_issue_path = repo_root / "scripts" / "next-issue.py"
    spec = importlib.util.spec_from_file_location("next_issue_module", next_issue_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_next_pr_resolves_current_backend_repo_and_skips_placeholder_client(
    monkeypatch,
):
    module = _load_next_pr_module()

    monkeypatch.delenv("TARGET_REPO", raising=False)
    monkeypatch.delenv("CLIENT_REPO", raising=False)
    monkeypatch.setattr(
        module, "_detect_current_repo", lambda: "blecx/softwareFactoryVscode"
    )

    repos = module._resolve_repos()

    assert repos["backend"] == "blecx/softwareFactoryVscode"
    assert repos["client"] == ""


def test_next_pr_returns_clear_error_for_explicit_missing_client_repo(
    monkeypatch, capsys
):
    module = _load_next_pr_module()

    monkeypatch.delenv("TARGET_REPO", raising=False)
    monkeypatch.delenv("CLIENT_REPO", raising=False)
    monkeypatch.setattr(
        module, "_detect_current_repo", lambda: "blecx/softwareFactoryVscode"
    )

    exit_code = module.main(["--repo", "client"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "no configured repository found for --repo client" in captured.err


def test_next_issue_selector_uses_defaults_when_tracking_file_is_missing(tmp_path):
    module = _load_next_issue_module()

    class DummyKnowledge:
        data = {"completed_issues": []}

        @staticmethod
        def get_adjusted_estimate(estimated_hours: float) -> float:
            return estimated_hours

    class DummyGitHub:
        @staticmethod
        def get_open_issues(limit: int = 100):
            return [
                {
                    "number": 12,
                    "title": "Test issue",
                    "state": "OPEN",
                }
            ]

        @staticmethod
        def is_issue_resolved(issue_number: int) -> bool:
            return True

        verbose = False

    missing_tracking = tmp_path / "missing-tracker.md"
    selector = module.IssueSelector(missing_tracking, DummyKnowledge(), DummyGitHub())

    assert selector.issues[0]["number"] == 12
    assert selector.issues[0]["phase"] == "Unknown"
    assert selector.issues[0]["priority"] == "Medium"
    assert selector.get_issue_context(12).startswith("No local Step-1 tracking file")


def test_next_issue_resolves_current_repo_when_target_repo_is_placeholder(
    monkeypatch,
):
    module = _load_next_issue_module()

    monkeypatch.setenv("TARGET_REPO", "YOUR_ORG/YOUR_REPO")
    monkeypatch.setattr(
        module, "_detect_current_repo", lambda: "blecx/softwareFactoryVscode"
    )

    assert module._resolve_github_repo() == "blecx/softwareFactoryVscode"
