import asyncio
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import yaml

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
    execute_approved_plan = (
        repo_root / ".github" / "agents" / "execute-approved-plan.md"
    )
    workflow_doc = repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md"

    assert queue_phase_2.exists()
    assert queue_backend.exists()
    assert execute_approved_plan.exists()
    assert not (repo_root / ".github" / "agents" / "continue-phase-2.md").exists()
    assert not (repo_root / ".github" / "agents" / "continue-backend.md").exists()
    assert workflow_doc.exists()

    assert "phase-2-queue-workflow" in queue_phase_2.read_text(encoding="utf-8")
    assert "backend-queue-workflow" in queue_backend.read_text(encoding="utf-8")
    assert (
        ".copilot/skills/approved-plan-execution-workflow/SKILL.md"
        in execute_approved_plan.read_text(encoding="utf-8")
    )

    workflow_doc_text = workflow_doc.read_text(encoding="utf-8")

    assert "@queue-backend" in workflow_doc_text
    assert "@queue-phase-2" in workflow_doc_text
    assert "@execute-approved-plan" in workflow_doc_text
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
    assert auto_approve["execute-approved-plan"] is True
    assert auto_approve["queue-backend"] is True
    assert auto_approve["queue-phase-2"] is True
    assert "continue-backend" not in auto_approve
    assert "continue-phase-2" not in auto_approve


def test_execute_approved_plan_skill_and_alias_routing_exist():
    repo_root = Path(__file__).parent.parent
    agent = (repo_root / ".github" / "agents" / "execute-approved-plan.md").read_text(
        encoding="utf-8"
    )
    skill = (
        repo_root
        / ".copilot"
        / "skills"
        / "approved-plan-execution-workflow"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    instructions = (repo_root / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8"
    )
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    approval_profiles = json.loads(
        (repo_root / ".copilot" / "config" / "vscode-approval-profiles.json").read_text(
            encoding="utf-8"
        )
    )

    lowered_agent = agent.lower()
    lowered_skill = skill.lower()
    lowered_instructions = instructions.lower()

    for phrase in [
        "execute the plan",
        "continue the plan",
        "run the approved queue",
        "work through the approved backlog",
        "finish the approved issue set",
    ]:
        assert phrase in lowered_agent
        assert phrase in lowered_skill

    assert ".tmp/github-issue-queue-state.md" in skill
    assert "single source of truth" in lowered_skill
    assert "resolve-issue` → `pr-merge`" in skill
    assert "do not stop merely because ci is pending" in lowered_skill
    assert "execute-approved-plan" in workflow_doc
    assert "run the approved queue" in lowered_instructions
    assert (
        approval_profiles["trusted-workflow"]["chat.tools.subagent.autoApprove"][
            "execute-approved-plan"
        ]
        is True
    )


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


def test_tasks_expose_local_ci_parity_default_precheck():
    repo_root = Path(__file__).parent.parent
    tasks = json.loads(
        (repo_root / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    )
    task_map = {task["label"]: task for task in tasks["tasks"]}

    ci_parity = task_map["✅ Validate: Local CI Parity"]
    assert ci_parity["command"] == "${workspaceFolder}/.venv/bin/python"
    assert ci_parity["args"] == ["${workspaceFolder}/scripts/local_ci_parity.py"]
    assert ci_parity["group"] == {"kind": "test", "isDefault": True}


def test_source_checkout_does_not_commit_static_mcp_server_urls():
    repo_root = Path(__file__).parent.parent
    settings = json.loads(
        (repo_root / ".vscode" / "settings.json").read_text(encoding="utf-8")
    )

    assert "mcp" not in settings


def test_canonical_agent_settings_template_matches_runtime_port_contract():
    repo_root = Path(__file__).parent.parent
    settings = json.loads(
        (repo_root / ".copilot" / "config" / "vscode-agent-settings.json").read_text(
            encoding="utf-8"
        )
    )
    servers = settings["workspace"]["mcp"]["servers"]

    assert servers["dockerCompose"]["url"] == "http://127.0.0.1:3016/mcp"
    assert servers["testRunner"]["url"] == "http://127.0.0.1:3015/mcp"


def test_docker_build_start_task_no_longer_auto_runs_on_folder_open():
    repo_root = Path(__file__).parent.parent
    tasks = json.loads(
        (repo_root / ".vscode" / "tasks.json").read_text(encoding="utf-8")
    )
    task_map = {task["label"]: task for task in tasks["tasks"]}

    docker_start = task_map["🐳 Docker: Build & Start"]

    assert docker_start.get("runOptions", {}).get("runOn") != "folderOpen"


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
    assert "scripts/local_ci_parity.py" in workflow_doc
    assert "scripts/verify_release_docs.py" in workflow_doc
    assert "scripts/factory_release.py write-manifest" in workflow_doc
    assert "./scripts/validate-pr-template.sh" in workflow_doc
    assert "./tests/run-integration-test.sh" in workflow_doc
    assert "--include-docker-build" in workflow_doc
    assert "ADR-005-Strong-Templating-Enforcement.md" in workflow_doc
    assert "ADR-006-Local-CI-Parity-Prechecks.md" in workflow_doc


def test_ordered_issue_checkpoint_contract_is_documented_without_prompt_hook():
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    guardrails_doc = (repo_root / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8"
    )
    resolve_skill = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    merge_skill = (
        repo_root / ".copilot" / "skills" / "pr-merge-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    approved_plan_skill = (
        repo_root
        / ".copilot"
        / "skills"
        / "approved-plan-execution-workflow"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert not (
        repo_root / ".github" / "hooks" / "github-issue-queue-guard.json"
    ).exists()
    assert not (repo_root / "scripts" / "github_issue_queue_guard.py").exists()

    assert "Deterministic queue checkpoint contract" in workflow_doc
    assert "does **not** use a global `UserPromptSubmit`" in workflow_doc

    for text in [
        workflow_doc,
        guardrails_doc,
        resolve_skill,
        merge_skill,
        approved_plan_skill,
    ]:
        assert ".tmp/github-issue-queue-state.md" in text

    assert (
        "There is no supported global `UserPromptSubmit` workflow hook"
        in guardrails_doc
    )
    assert "shared checkpoint" in guardrails_doc
    assert ".github/hooks/github-issue-queue-guard.json" not in resolve_skill
    assert ".github/hooks/github-issue-queue-guard.json" not in merge_skill


def test_queue_wrappers_share_one_canonical_issue_to_merge_process() -> None:
    repo_root = Path(__file__).parent.parent
    resolve_skill = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    merge_skill = (
        repo_root / ".copilot" / "skills" / "pr-merge-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    approved_plan_skill = (
        repo_root
        / ".copilot"
        / "skills"
        / "approved-plan-execution-workflow"
        / "SKILL.md"
    ).read_text(encoding="utf-8")
    backend_queue_skill = (
        repo_root / ".copilot" / "skills" / "backend-queue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    phase_2_queue_skill = (
        repo_root / ".copilot" / "skills" / "phase-2-queue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )

    assert "canonical implementation and PR-preparation half" in resolve_skill
    assert "canonical PR-validation, merge, and closeout half" in merge_skill
    assert "single source of truth" in approved_plan_skill.lower()
    assert "same canonical `resolve-issue` → `pr-merge` process" in backend_queue_skill
    assert "same canonical `resolve-issue` → `pr-merge` process" in phase_2_queue_skill
    assert "## Single source of truth for issue execution" in workflow_doc
    assert "Do not invent a separate “fix the PR” workflow." in workflow_doc


def test_interruption_recovery_assets_and_docs_exist():
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    queue_prompt = (
        repo_root / ".github" / "prompts" / "execute-github-issues-in-order.prompt.md"
    ).read_text(encoding="utf-8")
    recovery_prompt = (
        repo_root / ".github" / "prompts" / "resume-after-interruption.prompt.md"
    ).read_text(encoding="utf-8")
    recovery_skill = (
        repo_root
        / ".copilot"
        / "skills"
        / "interruption-recovery-workflow"
        / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert (repo_root / "scripts" / "capture_recovery_snapshot.py").exists()

    for text in [workflow_doc, queue_prompt, recovery_prompt, recovery_skill]:
        assert ".tmp/github-issue-queue-state.md" in text
        assert "capture_recovery_snapshot.py" in text

    assert ".tmp/interruption-recovery-snapshot.md" in workflow_doc
    assert ".tmp/interruption-recovery-snapshot.md" in queue_prompt
    assert ".tmp/interruption-recovery-snapshot.md" in recovery_prompt
    assert ".tmp/interruption-recovery-snapshot.md" in recovery_skill
    assert "factory_stack.py status" in workflow_doc
    assert "factory_stack.py status" in recovery_prompt
    assert "factory_stack.py status" in recovery_skill
    assert "window close/reopen" in workflow_doc
    assert "foreground task exit" in workflow_doc


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
    assert "./scripts/local_ci_parity.py" in adr_006
    assert "./scripts/verify_release_docs.py" in adr_006
    assert "factory_release.py write-manifest" in adr_006
    assert "./.venv/bin/black --check factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/isort --check-only factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/flake8 factory_runtime/ scripts/ tests/" in adr_006
    assert "./.venv/bin/pytest tests/" in adr_006
    assert "./tests/run-integration-test.sh" in adr_006
    assert "./scripts/validate-pr-template.sh <pr-body-file>" in adr_006
    assert "--include-docker-build" in adr_006


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


def test_workflow_doc_requires_reproducible_readiness_closeout_evidence() -> None:
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )

    assert "## Readiness closeout evidence discipline" in workflow_doc
    assert "documentation/evidence-alignment" in workflow_doc
    assert "./.venv/bin/python ./scripts/local_ci_parity.py" in workflow_doc
    assert "tests/test_regression.py -v" in workflow_doc
    assert "targeted Docker-backed validation" in workflow_doc
    assert "deferred items that remain out of scope" in workflow_doc
    assert "tests/README.md" in workflow_doc


def test_execution_surface_routing_contract_is_documented() -> None:
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    resolve_skill = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    instructions = (repo_root / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8"
    )

    assert "## Execution surfaces" in workflow_doc
    assert "**Source checkout**" in workflow_doc
    assert "**Generated workspace**" in workflow_doc
    assert "**Companion runtime metadata**" in workflow_doc
    assert "scripts/workspace_surface_guard.py" in workflow_doc
    assert "Host Project (Root)" in workflow_doc

    assert "scripts/workspace_surface_guard.py" in resolve_skill
    assert "source checkout as a second static runtime contract" in resolve_skill

    assert "Respect execution surfaces" in instructions
    assert "generated `software-factory.code-workspace` surface" in instructions


def test_mcp_first_tool_routing_guidance_is_documented() -> None:
    repo_root = Path(__file__).parent.parent
    instructions = (repo_root / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8"
    )
    prompt_skill = (
        repo_root / ".copilot" / "skills" / "prompt-quality-baseline" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "## 3. MCP-First Tool Routing" in instructions
    assert (
        "Broad terminal auto-approval settings do **not** change tool routing priority."
        in instructions
    )
    assert (
        "prefer the most specialized MCP server before generic terminal execution"
        in instructions
    )
    assert "Use the bash gateway only for allowlisted script workflows" in instructions
    assert "Treat generic terminal execution as a fallback-only path" in instructions

    assert (
        "When more than one MCP server or generic execution path could complete a task"
        in prompt_skill
    )
    assert (
        "Prefer the most specialized domain MCP server over generic servers and terminal/shell execution."
        in prompt_skill
    )
    assert "it is not the" in prompt_skill
    assert "default executor for arbitrary commands." in prompt_skill
    assert (
        "Treat generic terminal execution as a last-resort fallback only when no"
        in prompt_skill
    )
    assert (
        "auto-approve settings must not be treated as a reason to bypass MCP"
        in prompt_skill
    )


def test_noninteractive_terminal_guidance_is_documented() -> None:
    repo_root = Path(__file__).parent.parent
    workflow_doc = (repo_root / "docs" / "WORK-ISSUE-WORKFLOW.md").read_text(
        encoding="utf-8"
    )
    merge_skill = (
        repo_root / ".copilot" / "skills" / "pr-merge-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    issue_skill = (
        repo_root / ".copilot" / "skills" / "issue-creation-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")
    resolve_skill = (
        repo_root / ".copilot" / "skills" / "resolve-issue-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "## Non-interactive GitHub / terminal patterns" in workflow_doc
    assert "scripts/noninteractive_gh.py" in workflow_doc
    assert "gh pr checks --watch" in workflow_doc
    assert "heredoc" in workflow_doc
    assert "Long-running Docker/test output" in workflow_doc

    assert (
        "./.venv/bin/python ./scripts/noninteractive_gh.py pr-checks <PR_NUMBER>"
        in merge_skill
    )
    assert "gh pr checks --watch" in merge_skill
    assert "./.venv/bin/python ./scripts/noninteractive_gh.py issue-list" in issue_skill
    assert "heredoc-based Python command" in resolve_skill


def test_chat_session_troubleshooting_report_records_program_closeout() -> None:
    repo_root = Path(__file__).parent.parent
    report = (repo_root / "docs" / "CHAT-SESSION-TROUBLESHOOTING-REPORT.md").read_text(
        encoding="utf-8"
    )

    assert "# Chat session troubleshooting report" in report
    assert "umbrella issue `#61`" in report
    assert "Workflow drift and premature completion claims" in report
    assert "Interruption recovery gaps" in report
    assert "Wrong execution-surface choices" in report
    assert "Non-interactive terminal and GitHub CLI traps" in report
    assert "#62" in report
    assert "#63" in report
    assert "#64" in report
    assert "#65" in report
    assert "Final environment recheck on 2026-04-19" in report
    assert "210 passed, 2 skipped" in report
    assert "./.tmp/issue61_surface.out" in report
    assert "scripts/noninteractive_gh.py" in report


def test_historical_plans_and_reports_are_explicitly_labeled_before_any_archive_move() -> (
    None
):
    repo_root = Path(__file__).parent.parent
    harness_plan = (
        repo_root / "docs" / "HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md"
    ).read_text(encoding="utf-8")
    harness_backlog = (
        repo_root / "docs" / "HARNESS-NAMESPACE-IMPLEMENTATION-BACKLOG.md"
    ).read_text(encoding="utf-8")
    runtime_mitigation = (
        repo_root / "docs" / "MCP-RUNTIME-MITIGATION-PLAN.md"
    ).read_text(encoding="utf-8")
    report = (repo_root / "docs" / "CHAT-SESSION-TROUBLESHOOTING-REPORT.md").read_text(
        encoding="utf-8"
    )
    multi_workspace_plan = (
        repo_root
        / "docs"
        / "architecture"
        / "MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md"
    ).read_text(encoding="utf-8")

    assert "Historical sequencing / completed mitigation history" in harness_plan
    assert (
        "retained for traceability rather than as a living implementation plan"
        in harness_plan
    )
    assert "Historical sequencing / completed delivery backlog" in harness_backlog
    assert (
        "retained for traceability after the namespace migration backlog landed on `main`"
        in harness_backlog
    )
    assert "Historical sequencing / completed mitigation history" in runtime_mitigation
    assert "rather than a current execution plan" in runtime_mitigation
    assert "Historical closure record" in report
    assert (
        "not a living workflow specification or the current authority source for issue execution"
        in report
    )
    assert (
        "Historical sequencing plan with the ADR-008 rollout fulfilled on default branch"
        in multi_workspace_plan
    )


def test_setup_repo_doc_matches_current_ci_checks():
    repo_root = Path(__file__).parent.parent
    setup_doc = (repo_root / "docs" / "setup-github-repository.md").read_text(
        encoding="utf-8"
    )

    assert "Python Code Quality (Lint & Format)" in setup_doc
    assert "Architectural Boundary Tests" in setup_doc
    assert "PR Template Conformance" in setup_doc
    assert "Production Docs Contract" in setup_doc
    assert "Production Docker Build Parity" in setup_doc
    assert "Production Runtime Proofs" in setup_doc
    assert "Internal Production Gate — Docker Parity & Recovery Proofs" in setup_doc


def test_integration_regression_script_uses_repo_local_tmp_guardrail():
    repo_root = Path(__file__).parent.parent
    integration_script = (repo_root / "tests" / "run-integration-test.sh").read_text(
        encoding="utf-8"
    )

    assert 'MOCK_ROOT="$REPO_ROOT/.tmp/integration-test"' in integration_script
    assert 'mktemp -d "$MOCK_ROOT/mock-host-' in integration_script
    assert "/tmp/mock-host-" not in integration_script
    assert "--exclude=.tmp" in integration_script


def test_install_doc_locks_practical_per_workspace_baseline():
    repo_root = Path(__file__).parent.parent
    install_doc = (repo_root / "docs" / "INSTALL.md").read_text(encoding="utf-8")

    assert (
        "Use this guide when you need the full install/update/readiness authority."
        in install_doc
    )
    assert "This page keeps the long-form baseline in one place" in install_doc
    assert "## Supported practical baseline (what this guide promises)" in install_doc
    assert (
        "## Shared multi-tenant promotion gate (how to read release/docs status)"
        in install_doc
    )
    assert ".copilot/softwareFactoryVscode/" in install_doc
    assert "software-factory.code-workspace" in install_doc
    assert "factory_stack.py preflight" in install_doc
    assert "factory_stack.py activate" in install_doc
    assert "verify_factory_install.py --target . --runtime" in install_doc
    assert (
        "verify_factory_install.py --target . --runtime --check-vscode-mcp"
        in install_doc
    )
    assert "same manager-backed snapshot/readiness contract" in install_doc
    assert "additive evidence only" in install_doc
    assert "now-fulfilled `ADR-008` promotion gate" in install_doc
    assert "Current default-branch status: `fulfilled`" in install_doc
    assert "Historical releases may still use `open` or `advanced" in install_doc
    assert "groundwork` when they describe earlier repository states." in install_doc
    assert "## Readiness closeout snapshot (what is done vs deferred)" in install_doc
    assert "closes the MCP harness readiness baseline" in install_doc
    assert "Reproducible closeout evidence for this baseline is:" in install_doc
    assert "./.venv/bin/pytest tests/test_regression.py -v" in install_doc
    assert "./.venv/bin/python ./scripts/local_ci_parity.py" in install_doc
    assert (
        "./.venv/bin/python ./scripts/local_ci_parity.py --mode production"
        in install_doc
    )
    assert (
        "--mode production --production-group <docs-contract|docker-builds|runtime-proofs>"
        in install_doc
    )
    assert "strict_tenant_mode_blocks_cross_tenant_approval_leaks" in install_doc
    assert "stop_cleanup_retains_images_and_supports_restart" in install_doc
    assert "Still deferred after this readiness pass:" in install_doc
    assert "no release/version bump is implied" in install_doc
    assert "dynamic profile expansion" in install_doc
    assert "advanced groundwork" in install_doc
    assert "final architecture/documentation review" in install_doc
    assert "VS Code `1.116+`" in install_doc
    assert "GitHub Copilot is built in" in install_doc
    assert "Older VS Code releases" in install_doc
    assert "GitHub Pull Requests and Issues" in install_doc
    assert "chat.disableAIFeatures" in install_doc
    assert "now supports a bounded user-facing `suspended`" in install_doc
    assert "`factory_stack.py suspend`" in install_doc
    assert "`factory_stack.py resume`" in install_doc
    assert "`recovery_classification`" in install_doc
    assert "`completed_tool_call_boundary`" in install_doc
    assert "closing the window, or reopening later does not silently" in install_doc
    assert "reconcile/idempotent action" in install_doc
    assert "stop --remove-volumes" in install_doc
    assert "`delete-runtime` is the policy-driven trigger" in install_doc
    assert "retained build state rather than leaked runtime ownership" in install_doc
    assert "separate Docker operator action" in install_doc


def test_readme_tracks_version_aware_copilot_setup():
    repo_root = Path(__file__).parent.parent
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "**Latest release:** `2.6`" in readme
    assert ".github/releases/v2.6.md" in readme
    assert "docs/ROADMAP.md" in readme
    assert "docs/README.md" in readme
    assert "VS Code `1.116+`" in readme
    assert "GitHub Copilot is built in" in readme
    assert "Older VS Code releases" in readme
    assert "Copilot Free" in readme
    assert "GitHub Pull Requests and Issues extension" in readme
    assert "not required for Copilot chat, inline suggestions, or agents" in readme
    assert "The four primary docs split responsibilities on purpose:" in readme
    assert "project/release orientation and high-level routing" in readme
    assert "guided first-run operator walkthrough" in readme
    assert "terse task and command reference" in readme
    assert "promoted Docker E2E runtime proof lane" in readme


def test_primary_docs_use_summary_plus_linking_for_distinct_roles():
    repo_root = Path(__file__).parent.parent
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    install_doc = (repo_root / "docs" / "INSTALL.md").read_text(encoding="utf-8")
    handout = (repo_root / "docs" / "HANDOUT.md").read_text(encoding="utf-8")
    cheat_sheet = (repo_root / "docs" / "CHEAT_SHEET.md").read_text(encoding="utf-8")

    assert "full install/update/readiness authority" in readme
    assert (
        "Use this guide when you need the full install/update/readiness authority."
        in install_doc
    )
    assert "This handout is the guided first-run path" in handout
    assert "summarizes the deeper install/update/readiness detail" in handout
    assert "points repeat operators to" in handout
    assert (
        "Use this page when the install already exists and you want the shortest"
        in cheat_sheet
    )
    assert "For the first-time guided path" in cheat_sheet
    assert "for the full install/update/readiness authority" in cheat_sheet


def test_overview_docs_route_to_operator_runbooks() -> None:
    repo_root = Path(__file__).parent.parent
    readme = (repo_root / "README.md").read_text(encoding="utf-8")
    handout = (repo_root / "docs" / "HANDOUT.md").read_text(encoding="utf-8")
    cheat_sheet = (repo_root / "docs" / "CHEAT_SHEET.md").read_text(encoding="utf-8")

    assert "docs/ops/MONITORING.md" in readme
    assert "docs/ops/INCIDENT-RESPONSE.md" in readme
    assert "docs/ops/BACKUP-RESTORE.md" in readme

    assert "When you move from overview to action" in handout
    assert "ops/MONITORING.md" in handout
    assert "ops/INCIDENT-RESPONSE.md" in handout
    assert "ops/BACKUP-RESTORE.md" in handout

    assert (
        "When [`README.md`](../README.md) or [`HANDOUT.md`](HANDOUT.md)" in cheat_sheet
    )
    assert "ops/MONITORING.md" in cheat_sheet
    assert "ops/INCIDENT-RESPONSE.md" in cheat_sheet
    assert "ops/BACKUP-RESTORE.md" in cheat_sheet


def test_docs_readme_routes_audiences_without_competing_authority():
    repo_root = Path(__file__).parent.parent
    docs_readme = (repo_root / "docs" / "README.md").read_text(encoding="utf-8")

    assert "# Documentation index" in docs_readme
    assert "accepted ADRs are the normative architecture source" in docs_readme
    assert "do not override accepted ADRs" in docs_readme
    assert "## Start here by audience" in docs_readme
    assert "../README.md" in docs_readme
    assert "HANDOUT.md" in docs_readme
    assert "INSTALL.md" in docs_readme
    assert "CHEAT_SHEET.md" in docs_readme
    assert "WORK-ISSUE-WORKFLOW.md" in docs_readme
    assert "setup-github-repository.md" in docs_readme
    assert "maintainer/GUARDRAILS.md" in docs_readme
    assert "maintainer/AGENT-ENFORCEMENT-MAP.md" in docs_readme
    assert "maintainer/PROMPT-WORKFLOWS.md" in docs_readme
    assert "maintainer/APPROVAL-PROFILES.md" in docs_readme
    assert "architecture/INDEX.md" in docs_readme
    assert "architecture/ADR-INDEX.md" in docs_readme
    assert "ADR-013-Architecture-Authority-and-Plan-Separation.md" in docs_readme
    assert (
        "ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-"
        "Governance.md" in docs_readme
    )
    assert "ROADMAP.md" in docs_readme
    assert "https://github.com/blecx/softwareFactoryVscode/issues/163" in docs_readme
    assert "PRODUCTION-READINESS-PLAN.md" in docs_readme
    assert "## Planning document classification matrix" in docs_readme
    assert (
        "Accepted ADRs and current contract documents are intentionally not listed"
        in docs_readme
    )
    assert "[`ROADMAP.md`](ROADMAP.md) | Active roadmap |" in docs_readme
    assert (
        "[`PRODUCTION-READINESS-PLAN.md`](PRODUCTION-READINESS-PLAN.md) | "
        "Active supporting plan |" in docs_readme
    )
    assert (
        "[`HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md`]"
        "(HARNESS-NAMESPACE-MIGRATION-MITIGATION-PLAN.md) | Historical "
        "sequencing |" in docs_readme
    )
    assert (
        "[`architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md`]"
        "(architecture/MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md) | Historical "
        "sequencing |" in docs_readme
    )
    assert "## Historical and reference material" in docs_readme
    assert "MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md" in docs_readme


def test_maintainer_guardrail_catalog_indexes_current_enforcement_surfaces():
    repo_root = Path(__file__).parent.parent
    catalog = (repo_root / "docs" / "maintainer" / "GUARDRAILS.md").read_text(
        encoding="utf-8"
    )

    assert "# Maintainer guardrail catalog" in catalog
    assert "index/reference" in catalog
    assert "not a competing normative authority" in catalog
    assert "AGENT-ENFORCEMENT-MAP.md" in catalog
    assert "docs/WORK-ISSUE-WORKFLOW.md" in catalog
    assert ".github/copilot-instructions.md" in catalog
    assert ".copilot/skills/*" in catalog
    assert ".github/agents/*" in catalog
    assert "PROMPT-WORKFLOWS.md" in catalog
    assert ".github/prompts/*" in catalog
    assert "APPROVAL-PROFILES.md" in catalog
    assert ".github/ISSUE_TEMPLATE/feature_request.yml" in catalog
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in catalog
    assert ".github/pull_request_template.md" in catalog
    assert "ADR-013-Architecture-Authority-and-Plan-Separation.md" in catalog
    assert "ADR-005-Strong-Templating-Enforcement.md" in catalog
    assert "ADR-006-Local-CI-Parity-Prechecks.md" in catalog
    assert ".github/workflows/ci.yml" in catalog
    assert "configs/bash_gateway_policy.default.yml" in catalog
    assert "scripts/setup-low-approval.sh" in catalog
    assert "scripts/setup-vscode-agent-settings.py" in catalog


def test_maintainer_prompt_and_approval_reference_pages_track_current_sources():
    repo_root = Path(__file__).parent.parent
    prompt_reference = (
        repo_root / "docs" / "maintainer" / "PROMPT-WORKFLOWS.md"
    ).read_text(encoding="utf-8")
    approval_reference = (
        repo_root / "docs" / "maintainer" / "APPROVAL-PROFILES.md"
    ).read_text(encoding="utf-8")

    assert "# Prompt workflow reference" in prompt_reference
    assert "index/reference" in prompt_reference
    assert "not a competing normative authority" in prompt_reference
    assert "execute-github-issues-in-order.prompt.md" in prompt_reference
    assert "resume-after-interruption.prompt.md" in prompt_reference
    assert ".tmp/github-issue-queue-state.md" in prompt_reference
    assert ".tmp/interruption-recovery-snapshot.md" in prompt_reference
    assert "resolve-issue" in prompt_reference
    assert "pr-merge" in prompt_reference
    assert "execute-approved-plan" in prompt_reference
    assert "WORK-ISSUE-WORKFLOW.md" in prompt_reference
    assert "copilot-instructions.md" in prompt_reference

    assert "# Approval profiles reference" in approval_reference
    assert "index/reference" in approval_reference
    assert "not a competing normative authority" in approval_reference
    assert "vscode-approval-profiles.json" in approval_reference
    assert "chat.tools.subagent.autoApprove" in approval_reference
    assert "chat.tools.terminal.autoApprove" in approval_reference
    assert "safe" in approval_reference
    assert "trusted-workflow" in approval_reference
    assert "low-friction" in approval_reference
    assert "Configure Approval Profile (Safe)" in approval_reference
    assert "Configure Approval Profile (Trusted Workflow)" in approval_reference
    assert "Configure Approval Profile (Low-Friction)" in approval_reference
    assert "setup-low-approval.sh" in approval_reference
    assert "setup-vscode-agent-settings.py" in approval_reference
    assert "bash_gateway_policy.default.yml" in approval_reference


def test_agent_enforcement_map_routes_major_workflows_to_current_guardrail_sources():
    repo_root = Path(__file__).parent.parent
    enforcement_map = (
        repo_root / "docs" / "maintainer" / "AGENT-ENFORCEMENT-MAP.md"
    ).read_text(encoding="utf-8")

    assert "# Agent enforcement map" in enforcement_map
    assert "not a competing normative authority" in enforcement_map
    assert "create-issue" in enforcement_map
    assert "resolve-issue" in enforcement_map
    assert "pr-merge" in enforcement_map
    assert "execute-approved-plan" in enforcement_map
    assert "queue-backend" in enforcement_map
    assert "queue-phase-2" in enforcement_map
    assert "Plan" in enforcement_map
    assert "execute-github-issues-in-order.prompt.md" in enforcement_map
    assert "resume-after-interruption.prompt.md" in enforcement_map
    assert ".github/ISSUE_TEMPLATE/feature_request.yml" in enforcement_map
    assert ".github/ISSUE_TEMPLATE/bug_report.yml" in enforcement_map
    assert ".github/pull_request_template.md" in enforcement_map
    assert ".tmp/github-issue-queue-state.md" in enforcement_map
    assert "ADR-001-AI-Workflow-Guardrails.md" in enforcement_map
    assert "ADR-005-Strong-Templating-Enforcement.md" in enforcement_map
    assert "ADR-006-Local-CI-Parity-Prechecks.md" in enforcement_map
    assert "ADR-013-Architecture-Authority-and-Plan-Separation.md" in enforcement_map
    assert "WORK-ISSUE-WORKFLOW.md" in enforcement_map
    assert ".github/copilot-instructions.md" in enforcement_map


def test_docs_roadmap_separates_current_direction_from_historical_plans():
    repo_root = Path(__file__).parent.parent
    roadmap = (repo_root / "docs" / "ROADMAP.md").read_text(encoding="utf-8")

    assert "# Active roadmap summary" in roadmap
    assert "## Status" in roadmap
    assert "Active roadmap for the current documentation/readiness direction" in roadmap
    assert "current high-level roadmap" in roadmap
    assert "historical implementation plans" in roadmap
    assert "accepted ADRs remain the authority" in roadmap
    assert "released `2.6` story remains intact" in roadmap
    assert "umbrella issue `#163`" in roadmap
    assert "active-vs-historical classification of planning documents" in roadmap
    assert "PRODUCTION-READINESS.md" in roadmap
    assert "PRODUCTION-READINESS-PLAN.md" in roadmap
    assert "not the default current roadmap" in roadmap
    assert "MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md" in roadmap


def test_production_readiness_plan_is_marked_as_active_supporting_plan() -> None:
    repo_root = Path(__file__).parent.parent
    plan_doc = (repo_root / "docs" / "PRODUCTION-READINESS-PLAN.md").read_text(
        encoding="utf-8"
    )
    normalized_plan_doc = " ".join(plan_doc.split())

    assert "# Internal Production Readiness Plan" in plan_doc
    assert "## Status" in plan_doc
    assert (
        "Active supporting plan for the current internal, self-hosted readiness "
        "program" in normalized_plan_doc
    )
    assert (
        "remaining readiness work within the released `2.6` guardrails"
        in normalized_plan_doc
    )
    assert "It is not an ADR, not a release surface" in normalized_plan_doc
    assert (
        "not permission to broaden the supported production boundary"
        in normalized_plan_doc
    )


def test_release_bump_guardrails_define_current_release_sync_and_quality_bar():
    repo_root = Path(__file__).parent.parent
    instructions = (repo_root / ".github" / "copilot-instructions.md").read_text(
        encoding="utf-8"
    )
    template = (repo_root / ".github" / "releases" / "TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    skill = (
        repo_root / ".copilot" / "skills" / "release-bump-workflow" / "SKILL.md"
    ).read_text(encoding="utf-8")

    assert "README.md" in instructions
    assert "Definition of Done" in instructions
    assert "Quality metric" in instructions
    assert "## Current Release" in skill
    assert "## Definition of done" in skill
    assert "## Quality metrics" in skill
    assert "current-release surface consistency" in skill
    assert "README.md" in template
    assert "Current Release" in template


def test_tests_readme_maps_practical_baseline_coverage_surfaces():
    repo_root = Path(__file__).parent.parent
    tests_readme = (repo_root / "tests" / "README.md").read_text(encoding="utf-8")

    assert "## Practical baseline coverage map (P0/P1/P2 lock)" in tests_readme
    assert (
        "**Install/update contract:** `tests/test_factory_install.py`" in tests_readme
    )
    assert (
        "**Lifecycle/activation/verification guidance drift:** "
        "`tests/test_regression.py`" in tests_readme
    )
    assert (
        "**Host-isolation boundaries and subsystem mount safety:** "
        "`tests/run-integration-test.sh`" in tests_readme
    )
    assert "now-fulfilled ADR-008 shared multi-tenant promotion" in tests_readme
    assert "service-boundary isolation assertions" in tests_readme
    assert "`tests/test_throwaway_runtime_docker.py`" in tests_readme
    assert (
        "operator/runtime wording locks in `tests/test_regression.py`" in tests_readme
    )
    assert "## Lifecycle proof matrix (practical baseline)" in tests_readme
    assert "A → B → A activation / switch-back" in tests_readme
    assert "Stop → status" in tests_readme
    assert "Stop → verify" in tests_readme
    assert "Cleanup / `runtime-deleted`" in tests_readme
    assert "Reload / reopen recovery" in tests_readme
    assert "RUN_DOCKER_E2E=1" in tests_readme
    assert "not silently upgraded into the default local-CI-parity" in tests_readme
    assert (
        "./.venv/bin/python ./scripts/local_ci_parity.py --mode production"
        in tests_readme
    )
    assert "strict_tenant_mode_blocks_cross_tenant_approval_leaks" in tests_readme
    assert "stop_cleanup_retains_images_and_supports_restart" in tests_readme
    assert "## Readiness closeout evidence bundle" in tests_readme
    assert "./.venv/bin/pytest tests/test_regression.py -v" in tests_readme
    assert "./.venv/bin/python ./scripts/local_ci_parity.py" in tests_readme
    assert "activate_switch_back_keeps_one_active_workspace" in tests_readme
    assert "stop_cleanup_retains_images_and_supports_restart" in tests_readme
    assert "Still deferred after this readiness pass:" in tests_readme
    assert (
        "blanket claims that every service is globally shared by default"
        in tests_readme
    )


def test_tests_readme_documents_python_env_repair_path():
    repo_root = Path(__file__).parent.parent
    tests_readme = (repo_root / "tests" / "README.md").read_text(encoding="utf-8")

    assert "No module named ..." in tests_readme
    assert "./setup.sh" in tests_readme
    assert "requirements.dev.txt" in tests_readme
    assert "environment preflight" in tests_readme.lower()


def test_handout_and_cheat_sheet_reflect_explicit_runtime_lifecycle():
    repo_root = Path(__file__).parent.parent
    handout = (repo_root / "docs" / "HANDOUT.md").read_text(encoding="utf-8")
    cheat_sheet = (repo_root / "docs" / "CHEAT_SHEET.md").read_text(encoding="utf-8")
    normalized_handout = " ".join(handout.split())
    normalized_cheat_sheet = " ".join(cheat_sheet.split())

    assert "guided first-run path" in handout
    assert "CHEAT_SHEET.md" in handout
    assert "software-factory.code-workspace" in handout
    assert "factory_stack.py preflight" in handout
    assert "factory_stack.py start --build" in handout
    assert "VS Code / Copilot CLI workflow" in handout
    assert "workspace.code-workspace" not in handout
    assert "automatically start the background task" not in handout
    assert "advanced groundwork" in handout
    assert "current default branch now meets this threshold" in normalized_handout
    assert "VS Code `1.116+`" in handout
    assert "GitHub Pull Requests and Issues" in handout
    assert "same manager-backed readiness vocabulary" in handout
    assert "additive evidence only" in handout
    assert "does **not** automatically stop the runtime" in handout
    assert "does **not** auto-start the runtime either" in handout
    assert "foreground task exits while Docker containers keep running" in handout
    assert "reconcile/idempotent action" in handout
    assert "## ✅ Readiness closeout boundaries" in handout
    assert "current default-branch readiness baseline" in handout
    assert "./.venv/bin/pytest tests/test_regression.py -v" in handout
    assert "Still deferred after this readiness pass:" in handout
    assert "dynamic profile expansion during a running prompt" in handout

    assert "shortest task/command lookup" in normalized_cheat_sheet
    assert "HANDOUT.md" in cheat_sheet
    assert "INSTALL.md" in cheat_sheet
    assert "factory_stack.py activate" in cheat_sheet
    assert "factory_stack.py preflight" in cheat_sheet
    assert "refreshes generated runtime artifacts" in cheat_sheet
    assert "VS Code / Copilot CLI workflow" in cheat_sheet
    assert "shared_mode_status" in cheat_sheet
    assert "X-Workspace-ID" in cheat_sheet
    assert "PROJECT_WORKSPACE_ID" in cheat_sheet
    assert "stale registry data" not in cheat_sheet
    assert "advanced groundwork" in cheat_sheet
    assert "current default branch now meets this threshold" in normalized_cheat_sheet
    assert "VS Code `1.116+`" in cheat_sheet
    assert "GitHub Pull Requests and Issues" in cheat_sheet
    assert "same manager-backed readiness vocabulary" in cheat_sheet
    assert "additive evidence only" in cheat_sheet
    assert "now supports a bounded user-facing `suspended`" in cheat_sheet
    assert "`factory_stack.py suspend --completed-tool-call-boundary`" in cheat_sheet
    assert "`factory_stack.py resume`" in cheat_sheet
    assert "`recovery_classification`" in cheat_sheet
    assert "resume-safe" in cheat_sheet
    assert "does **not** automatically stop the runtime" in cheat_sheet
    assert "does **not** auto-start the runtime" in cheat_sheet
    assert "foreground task exits while containers still exist" in cheat_sheet
    assert "reconcile/idempotent action" in cheat_sheet
    assert "retain runtime metadata, volumes, and images" in cheat_sheet
    assert "destructive to metadata/data, not images" in cheat_sheet
    assert "`delete-runtime` is the policy-driven trigger" in cheat_sheet
    assert "Retained images after `stop` or `cleanup` are expected" in cheat_sheet
    assert "## ✅ Readiness closeout evidence" in cheat_sheet
    assert "./.venv/bin/pytest tests/test_regression.py -v" in cheat_sheet
    assert "./.venv/bin/python ./scripts/local_ci_parity.py" in cheat_sheet
    assert (
        "./.venv/bin/python ./scripts/local_ci_parity.py --mode production"
        in cheat_sheet
    )
    assert "--mode production --production-group docs-contract" in cheat_sheet
    assert "--mode production --production-group docker-builds" in cheat_sheet
    assert "--mode production --production-group runtime-proofs" in cheat_sheet
    assert "strict_tenant_mode_blocks_cross_tenant_approval_leaks" in cheat_sheet
    assert "supported baseline" in cheat_sheet
    assert "Still deferred after this readiness pass:" in cheat_sheet
    assert (
        "blanket claims that every service is globally shared by default" in cheat_sheet
    )


def test_runtime_manager_plan_marks_delivered_baseline_and_deferred_scope() -> None:
    repo_root = Path(__file__).parent.parent
    plan_doc = (
        repo_root
        / "docs"
        / "architecture"
        / "MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md"
    ).read_text(encoding="utf-8")

    assert (
        "Historical sequencing plan with the practical baseline delivered" in plan_doc
    )
    assert "## Still deferred after this readiness pass" in plan_doc
    assert (
        "`factory_runtime/mcp_runtime/` as the dedicated runtime-manager package"
        in plan_doc
    )
    assert (
        "manager-backed `preflight`, `status`, and runtime verification surfaces"
        in plan_doc
    )
    assert "## Readiness closeout evidence for this plan" in plan_doc
    assert "./.venv/bin/pytest tests/test_regression.py -v" in plan_doc
    assert "./.venv/bin/python ./scripts/local_ci_parity.py" in plan_doc
    assert "dynamic profile expansion during a running prompt" in plan_doc
    assert (
        "blanket claims of shared-service maturity beyond the explicit proofs"
        in plan_doc
    )


def test_adr_014_clarifies_current_suspend_boundary() -> None:
    repo_root = Path(__file__).parent.parent
    adr_014 = (
        repo_root
        / "docs"
        / "architecture"
        / "ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-Governance.md"
    ).read_text(encoding="utf-8")

    assert "`suspended` is a supported bounded lifecycle state" in adr_014
    assert "MUST present" in adr_014
    assert "`resume-safe`, `resume-unsafe`, or `manual-recovery-required`" in adr_014


def test_release_template_distinguishes_practical_vs_open_rollout_scope():
    repo_root = Path(__file__).parent.parent
    release_template = (repo_root / ".github" / "releases" / "TEMPLATE.md").read_text(
        encoding="utf-8"
    )

    assert "## Delivery status snapshot" in release_template
    assert re.search(
        r"\|\s*Scope\s*\|\s*Status\s*\|\s*Why it matters\s*\|",
        release_template,
    )
    assert "Practical per-workspace baseline" in release_template
    assert "Shared multi-tenant promotion (ADR-008 accepted)" in release_template
    assert "advanced groundwork" in release_template
    assert "Do not mark shared multi-tenant promotion as fulfilled" in release_template
    assert "## Shared multi-tenant promotion gate" in release_template
    assert "Before using `fulfilled`, verify" in release_template
    assert (
        "cross-tenant regression coverage and Docker-backed validation"
        in release_template
    )
    assert "final architecture/documentation review" in release_template


def test_multi_workspace_architecture_docs_capture_current_authority():
    repo_root = Path(__file__).parent.parent
    adr_013 = (
        repo_root
        / "docs"
        / "architecture"
        / "ADR-013-Architecture-Authority-and-Plan-Separation.md"
    ).read_text(encoding="utf-8")
    adr_009 = (
        repo_root
        / "docs"
        / "architecture"
        / "ADR-009-Active-Workspace-Registry-and-Lifecycle-Management.md"
    ).read_text(encoding="utf-8")
    architecture_doc = (
        repo_root / "docs" / "architecture" / "MULTI-WORKSPACE-MCP-ARCHITECTURE.md"
    ).read_text(encoding="utf-8")
    plan_doc = (
        repo_root
        / "docs"
        / "architecture"
        / "MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md"
    ).read_text(encoding="utf-8")

    assert (
        "implementation plan is the source of truth for sequencing" in adr_013.lower()
    )
    assert (
        "accepted adrs define architecture rules, terminology, and guardrails"
        in adr_013.lower()
    )

    assert "current VS Code workspace or Copilot CLI session" in adr_009
    assert (
        "MUST NOT be inferred merely from default localhost port ownership" in adr_009
    )

    assert "maintained architecture synthesis" in architecture_doc
    assert "ADR-008" in architecture_doc
    assert "Per `ADR-013`" in architecture_doc
    assert (
        "accepted `ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md`"
        in architecture_doc
    )
    assert "not a second active ADR-007 authority source" in architecture_doc
    assert (
        "The authoritative architectural definition of `active` lives in `ADR-009`"
        in architecture_doc
    )
    assert "activate` refreshes generated runtime artifacts" in architecture_doc
    assert "clear stale selection-lease metadata" in architecture_doc
    assert (
        "satisfies those rules for `mcp-memory`, `mcp-agent-bus`, and `approval-gate`"
        in architecture_doc
    )

    assert (
        "ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md" in plan_doc
    )
    assert "superseded historical note" in plan_doc
    assert "second active ADR-007 authority source" in plan_doc
    assert "maintained architecture synthesis" in plan_doc
    assert "Per `ADR-013`" in plan_doc
    assert (
        "the meaning of `installed`, `running`, and `active` comes from `ADR-009`"
        in plan_doc
    )
    assert "the ADR-008 rollout tracked here is now fulfilled on" in plan_doc


def test_architecture_index_clarifies_authority_and_duplicate_adr_007_numbering():
    repo_root = Path(__file__).parent.parent
    index_doc = (repo_root / "docs" / "architecture" / "INDEX.md").read_text(
        encoding="utf-8"
    )

    assert "ADR-INDEX.md" in index_doc
    assert "ADR-013-Architecture-Authority-and-Plan-Separation.md" in index_doc
    assert "Accepted ADRs" in index_doc
    assert "Maintained synthesis" in index_doc
    assert (
        "ADR-007-Workspace-Port-Allocation-and-Generated-MCP-Endpoints.md" in index_doc
    )
    assert "ADR-007-Multi-Workspace-and-Shared-Services.md" in index_doc
    assert "historical traceability" in index_doc
    assert "two active ADR-007 authority sources" in index_doc


def test_adr_catalog_summarizes_current_architecture_authority() -> None:
    repo_root = Path(__file__).parent.parent
    adr_index = (repo_root / "docs" / "architecture" / "ADR-INDEX.md").read_text(
        encoding="utf-8"
    )

    assert "# ADR catalog" in adr_index
    assert "complements [`INDEX.md`](INDEX.md)" in adr_index
    assert "accepted ADRs are the normative architecture source" in adr_index
    assert "## Status summary" in adr_index
    assert "| Accepted ADRs | 15 |" in adr_index
    assert "| Superseded historical ADR notes | 1 |" in adr_index
    assert "| Proposed ADRs | 0 |" in adr_index
    assert "## Accepted ADR catalog" in adr_index
    assert "ADR-001-AI-Workflow-Guardrails.md" in adr_index
    assert "ADR-013-Architecture-Authority-and-Plan-Separation.md" in adr_index
    assert (
        "ADR-014-MCP-Workspace-Runtime-Lifecycle-Prompt-Coordination-and-Resource-"
        "Governance.md" in adr_index
    )
    assert (
        "ADR-015-Quota-Governance-Contract-for-Multi-Requester-LLM-Access.md"
        in adr_index
    )
    assert "## Historical note on duplicate ADR-007 numbering" in adr_index
    assert "ADR-007-Multi-Workspace-and-Shared-Services.md" in adr_index
    assert "must not be used as a current architecture authority" in adr_index


def test_stabilization_plan_and_superseded_tenancy_draft_are_explicit():
    repo_root = Path(__file__).parent.parent
    superseded_adr = (
        repo_root
        / "docs"
        / "architecture"
        / "ADR-007-Multi-Workspace-and-Shared-Services.md"
    ).read_text(encoding="utf-8")
    plan_doc = (
        repo_root
        / "docs"
        / "architecture"
        / "MULTI-WORKSPACE-MCP-IMPLEMENTATION-PLAN.md"
    ).read_text(encoding="utf-8")

    assert "## Status" in superseded_adr
    assert "Superseded" in superseded_adr
    assert "MUST NOT be used as a normative architecture source" in superseded_adr
    assert "historical traceability" in superseded_adr
    assert "active ADR-007 authority source" in superseded_adr

    assert "## Immediate Stabilization Rework Order" in plan_doc
    assert "## Execution Guardrails for This Rework" in plan_doc
    assert "## Mitigation Map and Current Resolution Status" in plan_doc
    assert "## Accepted ADR to Production Rollout Path" in plan_doc
    assert (
        "## Historical delivery split while shared-service rollout remained open"
        in plan_doc
    )
    assert re.search(
        r"\|\s*Scope\s*\|\s*Status\s*\|\s*Priority now\s*\|\s*Why it matters\s*\|",
        plan_doc,
    )
    assert "Fulfilled on default branch" in plan_doc
    assert "## Practical execution plan for a working system" in plan_doc
    assert "### Priority 0: New repo onboarding, install, and update safety" in plan_doc
    assert (
        "### Priority 1: Lifecycle truth, activation behavior, and per-workspace verification"
        in plan_doc
    )
    assert (
        "### Priority 2: Docs, regression coverage, and day-two operator confidence"
        in plan_doc
    )
    assert "### Shared multi-tenant rollout completion note" in plan_doc
    assert "## Program-level definition of done" in plan_doc
    assert "## Mandatory quality gates for this rework" in plan_doc
    assert "## Transition, update, and upgrade safety rules" in plan_doc
    assert "MUST follow the suggested order of attack" in plan_doc
    assert "MUST NOT introduce new architecture decisions" in plan_doc
    assert "MUST preserve the current runtime feature surface" in plan_doc
    assert "MUST NOT remove existing runtime features as a shortcut" in plan_doc
    assert "Resolved by this rework" in plan_doc
    assert "Do the practical per-workspace priorities first." in plan_doc
    assert (
        "Shared multi-tenant promotion of `mcp-memory`, `mcp-agent-bus`, and `approval-gate`"
        in plan_doc
    )
    assert "Not promoted in this rework" in plan_doc
    assert "## ADR-008 rollout mitigation program" in plan_doc
    assert "### Track 1: Promotion boundary and shared-mode contract" in plan_doc
    assert "### Track 8: Final promotion gate" in plan_doc
    assert "Only after the rollout criteria are verified" in plan_doc
    assert "duplicate ADR-007 filename" in plan_doc


def test_mcp_runtime_manager_plan_is_explicitly_non_normative():
    repo_root = Path(__file__).parent.parent
    plan_doc = (
        repo_root
        / "docs"
        / "architecture"
        / "MCP-RUNTIME-MANAGER-IMPLEMENTATION-PLAN.md"
    ).read_text(encoding="utf-8")

    assert "## Status" in plan_doc
    assert (
        "Historical sequencing plan with the practical baseline delivered" in plan_doc
    )
    assert "Read the phase breakdown below as sequencing history" in plan_doc
    assert "implementation plan, not an ADR" in plan_doc
    assert "Per `ADR-013`" in plan_doc
    assert "Per `ADR-014`" in plan_doc
    assert "MUST NOT be cited as a competing architecture source" in plan_doc
    assert "## Execution guardrails" in plan_doc
    assert "## Target module layout for the first implementation" in plan_doc
    assert "### Phase 1: Establish the manager package and contract" in plan_doc
    assert "#### Phase 1 tasks" in plan_doc
    assert "### Phase 2: Move runtime truth behind the manager" in plan_doc
    assert "#### Phase 2 tasks" in plan_doc
    assert "### Phase 3: Remove runtime authority from the harness layer" in plan_doc
    assert "#### Phase 3 tasks" in plan_doc
    assert (
        "### Phase 4: Land the bounded repair and cleanup/delete-runtime baseline"
        in plan_doc
    )
    assert "#### Phase 4 tasks" in plan_doc
    assert (
        "## Recommended execution order for the next implementation stretch" in plan_doc
    )
    assert "## Quality gates" in plan_doc
    assert "## First slice recommendation" in plan_doc


def test_bash_gateway_default_policy_matches_profile_schema():
    repo_root = Path(__file__).parent.parent
    policy_path = repo_root / "configs" / "bash_gateway_policy.default.yml"

    from factory_runtime.apps.mcp.bash_gateway.policy import BashGatewayPolicy

    data = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    policy = BashGatewayPolicy.from_dict(data)

    assert set(policy.profiles) == {"safe-readonly", "repo-maintenance"}
    assert "scripts/validate-pr-template.sh" in policy.profiles["safe-readonly"].scripts
    assert "setup.sh" in policy.profiles["repo-maintenance"].scripts


def test_mcp_multi_client_performs_streamable_http_handshake():
    from factory_runtime.agents.mcp_client import MCPMultiClient

    session_id = "session-123"
    state = {
        "initialized": False,
        "notified": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == httpx.URL("http://test-server/mcp")
        assert request.headers["accept"] == "application/json, text/event-stream"
        assert request.headers["mcp-protocol-version"] == "2025-03-26"
        payload = json.loads(request.content.decode("utf-8"))
        method = payload.get("method")

        if method == "initialize":
            state["initialized"] = True
            return httpx.Response(
                200,
                headers={"mcp-session-id": session_id},
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "mock", "version": "1.0"},
                    },
                },
            )

        if request.headers.get("mcp-session-id") != session_id:
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": "server-error",
                    "error": {
                        "code": -32600,
                        "message": "Bad Request: Missing session ID",
                    },
                },
            )

        if method == "notifications/initialized":
            state["notified"] = True
            return httpx.Response(202, text="")

        if not state["initialized"] or not state["notified"]:
            return httpx.Response(
                400,
                json={
                    "jsonrpc": "2.0",
                    "id": payload.get("id", "server-error"),
                    "error": {"code": -32600, "message": "Handshake incomplete"},
                },
            )

        if method == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "ping_tool",
                                "description": "Ping",
                                "inputSchema": {"type": "object"},
                            }
                        ]
                    },
                },
            )

        if method == "tools/call":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "result": {"ok": True, "echo": payload["params"]},
                },
            )

        return httpx.Response(404, text="unexpected")

    async def run_test() -> None:
        transport = httpx.MockTransport(handler)
        async with MCPMultiClient(
            [{"name": "mock", "url": "http://test-server"}],
            transport=transport,
        ) as client:
            tools = client.list_tools()
            assert [tool.name for tool in tools] == ["ping_tool"]

            result = await client.call_tool("ping_tool", {"value": "pong"})
            assert result == {
                "ok": True,
                "echo": {"name": "ping_tool", "arguments": {"value": "pong"}},
            }

    asyncio.run(run_test())
    assert state == {"initialized": True, "notified": True}


def test_mcp_multi_client_exports_openai_tool_definitions():
    from factory_runtime.agents.mcp_client import MCPMultiClient, ToolInfo

    client = MCPMultiClient([])
    client._tools = {
        "ping_tool": ToolInfo(
            name="ping_tool",
            description="Ping",
            server_name="mock",
            server_url="http://test-server",
            input_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
            },
        )
    }

    definitions = client.get_all_tool_definitions()

    assert definitions == [
        {
            "type": "function",
            "function": {
                "name": "ping_tool",
                "description": "Ping",
                "parameters": {
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
            },
        }
    ]


def test_approval_gate_entrypoint_uses_factory_runtime_module_path():
    repo_root = Path(__file__).parent.parent
    approval_gate = (
        repo_root / "factory_runtime" / "apps" / "approval_gate" / "main.py"
    ).read_text(encoding="utf-8")

    assert "factory_runtime.apps.approval_gate.main:app" in approval_gate
    assert "uvicorn apps.approval_gate.main:app" not in approval_gate
    assert "python -m apps.approval_gate.main" not in approval_gate


def _load_next_pr_module():
    repo_root = Path(__file__).parent.parent
    next_pr_path = repo_root / "scripts" / "next-pr.py"
    spec = importlib.util.spec_from_file_location("next_pr_module", next_pr_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_next_issue_module():
    repo_root = Path(__file__).parent.parent
    next_issue_path = repo_root / "scripts" / "next-issue.py"
    spec = importlib.util.spec_from_file_location("next_issue_module", next_issue_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_local_ci_parity_module():
    repo_root = Path(__file__).parent.parent
    local_ci_path = repo_root / "scripts" / "local_ci_parity.py"
    spec = importlib.util.spec_from_file_location(
        "local_ci_parity_module", local_ci_path
    )
    assert spec is not None
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


def test_local_ci_parity_reports_findings_list_and_improvement_plan(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    executed_commands: list[tuple[str, ...]] = []

    def _fake_run_command(command, *, cwd):
        del cwd
        command_tuple = tuple(command)
        executed_commands.append(command_tuple)

        if command_tuple[1:3] == ("-m", "black"):
            return subprocess.CompletedProcess(
                list(command_tuple),
                1,
                stdout="",
                stderr="would reformat scripts/demo.py\n",
            )

        return subprocess.CompletedProcess(
            list(command_tuple),
            0,
            stdout="ok\n",
            stderr="",
        )

    monkeypatch.setattr(module, "run_command", _fake_run_command)

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--skip-integration",
            "--skip-pr-template-check",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert any("black" in command for command in executed_commands)
    assert any("flake8" in command for command in executed_commands)

    assert "Findings" in captured.out
    assert "[ERROR] Black format check" in captured.out
    assert "[WARNING] Integration regression" in captured.out
    assert "[WARNING] PR-template format validation" in captured.out
    assert "[WARNING] Docker image build parity" in captured.out
    assert "Improvement plan" in captured.out
    assert (
        "Run Black on `factory_runtime/`, `scripts/`, and `tests/`, then review the diffs."
        in captured.out
    )
    assert (
        "Run the standard precheck again without `--skip-integration` before "
        "finalizing the PR." in captured.out
    )
    assert "would reformat scripts/demo.py" in captured.err


def test_local_ci_parity_warnings_do_not_fail_the_standard_precheck(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Summary: 0 error(s), 1 warning(s)." in captured.out
    assert "[WARNING] Docker image build parity" in captured.out
    assert "--mode production" in captured.out
    assert "Improvement plan" in captured.out
    assert "passed with 1 warning(s)" in captured.out


def test_local_ci_parity_production_mode_runs_blocking_docker_build_parity(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    docker_build_calls: list[Path] = []
    docker_e2e_calls: list[tuple[Path, str]] = []

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    def _fake_run_docker_build_validation(repo_root: Path):
        docker_build_calls.append(repo_root)
        return []

    def _fake_run_docker_e2e_validation(repo_root: Path, *, python_executable: str):
        docker_e2e_calls.append((repo_root, python_executable))
        return []

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        _fake_run_docker_build_validation,
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        _fake_run_docker_e2e_validation,
    )
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert docker_build_calls == [tmp_path.resolve()]
    assert docker_e2e_calls == [(tmp_path.resolve(), sys.executable)]
    assert "mode=production" in captured.out
    assert "[WARNING] Docker image build parity" not in captured.out
    assert "passed with no warnings or errors" in captured.out


def test_local_ci_parity_production_mode_reports_docker_build_failures_as_blocking(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    docker_e2e_called = False

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    def _fake_run_docker_e2e_validation(repo_root: Path, *, python_executable: str):
        nonlocal docker_e2e_called
        del repo_root, python_executable
        docker_e2e_called = True
        return []

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        lambda repo_root: [
            module.Finding(
                severity="error",
                name="Docker image build parity",
                summary="Docker image build validation failed for `demo-service`.",
                remediation="Inspect `docker/demo-service/Dockerfile` and rerun the production parity command.",
                command=(
                    "docker",
                    "build",
                    "-f",
                    "docker/demo-service/Dockerfile",
                    ".",
                ),
                returncode=1,
            )
        ],
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        _fake_run_docker_e2e_validation,
    )
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[ERROR] Docker image build parity" in captured.out
    assert "demo-service" in captured.out
    assert "--mode production" in captured.out
    assert not docker_e2e_called


def test_local_ci_parity_include_docker_build_alias_still_runs_without_warning(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    docker_calls: list[Path] = []

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    def _fake_run_docker_build_validation(repo_root: Path):
        docker_calls.append(repo_root)
        return []

    def _fail_if_docker_e2e_runs(repo_root: Path, *, python_executable: str):
        del repo_root, python_executable
        raise AssertionError(
            "docker E2E lane should not run for --include-docker-build"
        )

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        _fake_run_docker_build_validation,
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        _fail_if_docker_e2e_runs,
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--include-docker-build",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert docker_calls == [tmp_path.resolve()]
    assert "[WARNING] Docker image build parity" not in captured.out
    assert "passed with no warnings or errors" in captured.out


def test_local_ci_parity_production_mode_reports_docker_e2e_failures_as_blocking(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(module, "run_docker_build_validation", lambda repo_root: [])
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: [
            module.Finding(
                severity="error",
                name="Docker E2E runtime proof lane",
                summary=(
                    "The promoted Docker E2E runtime proof lane reported failures "
                    "for at least one of the blocking strict-tenant, stop/cleanup, "
                    "and backup/restore scenarios."
                ),
                remediation="Investigate the promoted Docker E2E scenarios and rerun production parity.",
                command=(
                    "env",
                    "RUN_DOCKER_E2E=1",
                    python_executable,
                    "-m",
                    "pytest",
                    module.DOCKER_E2E_TEST_FILE,
                    "-k",
                    module.PRODUCTION_DOCKER_E2E_KEYWORD_EXPR,
                    "-v",
                ),
                returncode=1,
            )
        ],
    )
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[ERROR] Docker E2E runtime proof lane" in captured.out
    assert "RUN_DOCKER_E2E=1" in captured.out
    assert module.PRODUCTION_DOCKER_E2E_KEYWORD_EXPR in captured.out


def test_run_docker_e2e_validation_sets_env_and_selected_pytest_filter(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    call: dict[str, object] = {}

    def _fake_subprocess_run(
        command,
        *,
        cwd,
        check,
        capture_output,
        text,
        env,
    ):
        call["command"] = command
        call["cwd"] = cwd
        call["check"] = check
        call["capture_output"] = capture_output
        call["text"] = text
        call["run_docker_e2e"] = env.get("RUN_DOCKER_E2E")
        return subprocess.CompletedProcess(command, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(module.subprocess, "run", _fake_subprocess_run)

    findings = module.run_docker_e2e_validation(
        tmp_path,
        python_executable="/custom/python",
    )

    assert findings == []
    assert call["command"] == [
        "/custom/python",
        "-m",
        "pytest",
        module.DOCKER_E2E_TEST_FILE,
        "-k",
        module.PRODUCTION_DOCKER_E2E_KEYWORD_EXPR,
        "-v",
    ]
    assert call["cwd"] == str(tmp_path)
    assert call["check"] is False
    assert call["capture_output"] is True
    assert call["text"] is True
    assert call["run_docker_e2e"] == "1"
    transcript = (
        tmp_path
        / ".tmp"
        / "production-readiness"
        / module.DOCKER_E2E_LATEST_LOG_FILENAME
    )
    assert transcript.exists()
    transcript_text = transcript.read_text(encoding="utf-8")
    assert module.DOCKER_E2E_TEST_FILE in transcript_text
    assert "Exit code: 0" in transcript_text


def test_run_docker_bind_mount_ownership_parity_probe_reports_host_mapped_writes(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    probe_root = tmp_path / ".tmp" / "production-readiness" / "docker-bind-mount-parity"
    cleanup_commands: list[tuple[str, ...]] = []

    def _fake_run_command(command, *, cwd):
        del cwd
        command_tuple = tuple(command)
        if "chown -R" in command_tuple[-1]:
            cleanup_commands.append(command_tuple)
            return subprocess.CompletedProcess(
                list(command_tuple),
                0,
                stdout="",
                stderr="",
            )

        nested_dir = probe_root / "nested"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "from-container").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            list(command_tuple),
            0,
            stdout="ok\n",
            stderr="",
        )

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(module, "run_command", _fake_run_command)

    finding = module.run_docker_bind_mount_ownership_parity_probe(tmp_path)

    assert finding is not None
    assert finding.name == "Docker bind-mount ownership parity"
    assert "differ from GitHub-hosted runners" in finding.summary
    assert (
        cleanup_commands
    ), "probe cleanup must restore writable ownership after the probe"
    transcript = (
        tmp_path
        / ".tmp"
        / "production-readiness"
        / module.DOCKER_BIND_MOUNT_PARITY_LOG_FILENAME
    )
    assert transcript.exists()


def test_run_docker_bind_mount_ownership_parity_probe_accepts_non_writable_nested_paths(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    probe_root = tmp_path / ".tmp" / "production-readiness" / "docker-bind-mount-parity"

    def _fake_run_command(command, *, cwd):
        del cwd
        command_tuple = tuple(command)
        if "chown -R" in command_tuple[-1]:
            return subprocess.CompletedProcess(
                list(command_tuple),
                0,
                stdout="",
                stderr="",
            )

        nested_dir = probe_root / "nested"
        nested_dir.mkdir(parents=True, exist_ok=True)
        (nested_dir / "from-container").write_text("ok\n", encoding="utf-8")
        return subprocess.CompletedProcess(
            list(command_tuple),
            0,
            stdout="ok\n",
            stderr="",
        )

    real_access = module.os.access

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/docker")
    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module.os,
        "access",
        lambda path, mode: (
            False
            if str(path).startswith(str(probe_root / "nested"))
            else real_access(path, mode)
        ),
    )

    finding = module.run_docker_bind_mount_ownership_parity_probe(tmp_path)

    assert finding is None


def test_local_ci_parity_fresh_checkout_bootstraps_and_reexecutes(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    snapshot_path = tmp_path / "fresh-checkout"
    snapshot_path.mkdir(parents=True, exist_ok=True)
    calls: list[tuple[tuple[str, ...], Path]] = []

    monkeypatch.setattr(
        module,
        "create_fresh_checkout_snapshot",
        lambda repo_root, *, head_rev: snapshot_path,
    )
    monkeypatch.setattr(
        module, "resolve_head_revision", lambda repo_root, head_rev: "deadbeef"
    )
    monkeypatch.setattr(
        module, "worktree_has_uncommitted_changes", lambda repo_root: True
    )
    monkeypatch.setattr(
        module,
        "run_docker_bind_mount_ownership_parity_probe",
        lambda repo_root: None,
    )

    def _fake_run_command(command, *, cwd):
        command_tuple = tuple(command)
        calls.append((command_tuple, cwd))
        return subprocess.CompletedProcess(
            list(command_tuple), 0, stdout="ok\n", stderr=""
        )

    monkeypatch.setattr(module, "run_command", _fake_run_command)

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
            "--fresh-checkout",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls[0] == (("bash", "./setup.sh"), snapshot_path)
    child_command, child_cwd = calls[1]
    assert child_cwd == snapshot_path
    assert child_command[:2] == ("./.venv/bin/python", "./scripts/local_ci_parity.py")
    assert "--fresh-checkout" not in child_command
    assert "--python" in child_command
    assert "./.venv/bin/python" in child_command
    assert "snapshot_path=" in captured.out
    assert "committed HEAD only" in captured.out


def test_local_ci_parity_fresh_checkout_production_mode_blocks_on_docker_ownership_gap(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    monkeypatch.setattr(
        module,
        "run_docker_bind_mount_ownership_parity_probe",
        lambda repo_root: module.Finding(
            severity="error",
            name="Docker bind-mount ownership parity",
            summary=(
                "Local Docker bind-mount ownership semantics differ from "
                "GitHub-hosted runners."
            ),
            remediation=(
                "Run exact fresh-checkout parity on a rootful Docker daemon/context."
            ),
        ),
    )
    monkeypatch.setattr(
        module,
        "create_fresh_checkout_snapshot",
        lambda repo_root, *, head_rev: (_ for _ in ()).throw(
            AssertionError(
                "fresh-checkout snapshot must not be created after a parity gap"
            )
        ),
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
            "--fresh-checkout",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[ERROR] Docker bind-mount ownership parity" in captured.out
    assert "rootful Docker daemon/context" in captured.out


def test_production_readiness_docs_name_promoted_docker_e2e_gate():
    repo_root = Path(__file__).parent.parent
    readiness_doc = (repo_root / "docs" / "PRODUCTION-READINESS.md").read_text(
        encoding="utf-8"
    )

    assert (
        "./.venv/bin/python ./scripts/local_ci_parity.py --mode production"
        in readiness_doc
    )
    assert "strict_tenant_mode_blocks_cross_tenant_approval_leaks" in readiness_doc
    assert "stop_cleanup_retains_images_and_supports_restart" in readiness_doc
    assert (
        "backup_restore_roundtrip_recovers_state_and_runtime_contract" in readiness_doc
    )
    assert "activate_switch_back_keeps_one_active_workspace" in readiness_doc
    assert ".tmp/production-readiness/latest.md" in readiness_doc
    assert "three consecutive clean runs" in readiness_doc
    assert "--fresh-checkout" in readiness_doc
    assert "Production Docs Contract" in readiness_doc
    assert "Production Docker Build Parity" in readiness_doc
    assert "Production Runtime Proofs" in readiness_doc
    assert "Internal Production Gate — Docker Parity & Recovery Proofs" in readiness_doc


def test_local_ci_parity_production_mode_reports_missing_required_docs_as_blocking(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(module, "run_docker_build_validation", lambda repo_root: [])
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[ERROR] Required internal-production docs/runbooks" in captured.out
    assert "docs/PRODUCTION-READINESS.md" in captured.out
    assert "docs/ops/BACKUP-RESTORE.md" in captured.out


def test_local_ci_parity_production_mode_writes_signoff_bundle_and_tracks_green_streak(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    for relative_path in module.PRODUCTION_READINESS_REQUIRED_DOCS:
        doc_path = tmp_path / relative_path
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(f"# {relative_path}\n", encoding="utf-8")

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(module, "run_docker_build_validation", lambda repo_root: [])
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    assert exit_code == 0

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    latest_report = json.loads(
        (tmp_path / ".tmp" / "production-readiness" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    latest_summary = (
        tmp_path / ".tmp" / "production-readiness" / "latest.md"
    ).read_text(encoding="utf-8")
    history = json.loads(
        (tmp_path / ".tmp" / "production-readiness" / "history.json").read_text(
            encoding="utf-8"
        )
    )

    assert latest_report["scope"] == module.PRODUCTION_READINESS_SCOPE
    assert latest_report["status"] == "pass"
    assert latest_report["green_run"] is True
    assert latest_report["current_green_streak"] == 2
    assert (
        latest_report["final_signoff_status"] == "pending-three-consecutive-green-runs"
    )
    assert "Consecutive clean runs: `2/3`" in latest_summary
    assert (
        "Internal production gate — Docker parity & recovery proofs" in latest_summary
    )
    assert (
        "Internal production gate sign-off — Docker parity & recovery proofs"
        in captured.out
    )
    assert history["current_streak"]["count"] == 2
    assert len(history["runs"]) == 2


def test_local_ci_parity_production_diagnostic_group_docs_contract_only(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    call_order: list[str] = []

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCS_CONTRACT)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCKER_BUILDS)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: call_order.append(
            module.PRODUCTION_GROUP_RUNTIME_PROOFS
        )
        or [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
            "--production-group",
            module.PRODUCTION_GROUP_DOCS_CONTRACT,
        ]
    )

    assert exit_code == 0
    assert call_order == [module.PRODUCTION_GROUP_DOCS_CONTRACT]
    assert not (tmp_path / ".tmp" / "production-readiness" / "latest.json").exists()


def test_local_ci_parity_production_groups_only_skips_default_prechecks(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    call_order: list[str] = []
    executed_commands: list[tuple[str, ...]] = []

    def _fake_run_command(command, *, cwd):
        del cwd
        command_tuple = tuple(command)
        executed_commands.append(command_tuple)
        return subprocess.CompletedProcess(
            list(command_tuple), 0, stdout="ok\n", stderr=""
        )

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCS_CONTRACT)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCKER_BUILDS)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: call_order.append(
            module.PRODUCTION_GROUP_RUNTIME_PROOFS
        )
        or [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
            "--production-group",
            module.PRODUCTION_GROUP_DOCS_CONTRACT,
            "--production-groups-only",
        ]
    )

    assert exit_code == 0
    assert call_order == [module.PRODUCTION_GROUP_DOCS_CONTRACT]
    assert not any(command[1:3] == ("-m", "black") for command in executed_commands)
    assert not any(command[1:3] == ("-m", "pytest") for command in executed_commands)


def test_local_ci_parity_rejects_production_groups_only_in_standard_mode(
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--production-groups-only",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "only supported with `--mode production`" in captured.out


def test_local_ci_parity_production_aggregate_runs_named_groups_in_canonical_order(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()
    call_order: list[str] = []

    for relative_path in module.PRODUCTION_READINESS_REQUIRED_DOCS:
        doc_path = tmp_path / relative_path
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(f"# {relative_path}\n", encoding="utf-8")

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCS_CONTRACT)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_build_validation",
        lambda repo_root: call_order.append(module.PRODUCTION_GROUP_DOCKER_BUILDS)
        or [],
    )
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: call_order.append(
            module.PRODUCTION_GROUP_RUNTIME_PROOFS
        )
        or [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )

    assert exit_code == 0
    assert call_order == list(module.PRODUCTION_GROUP_ORDER)
    latest_report = json.loads(
        (tmp_path / ".tmp" / "production-readiness" / "latest.json").read_text(
            encoding="utf-8"
        )
    )
    assert latest_report["production_groups_executed"] == list(
        module.PRODUCTION_GROUP_ORDER
    )


def test_local_ci_parity_diagnostic_group_run_keeps_aggregate_bundle_continuity(
    monkeypatch,
    tmp_path: Path,
):
    module = _load_local_ci_parity_module()

    for relative_path in module.PRODUCTION_READINESS_REQUIRED_DOCS:
        doc_path = tmp_path / relative_path
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(f"# {relative_path}\n", encoding="utf-8")

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(module, "run_docker_build_validation", lambda repo_root: [])
    monkeypatch.setattr(
        module,
        "run_docker_e2e_validation",
        lambda repo_root, *, python_executable: [],
    )

    aggregate_exit = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    assert aggregate_exit == 0

    latest_path = tmp_path / ".tmp" / "production-readiness" / "latest.json"
    aggregate_latest = json.loads(latest_path.read_text(encoding="utf-8"))

    diagnostic_exit = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
            "--production-group",
            module.PRODUCTION_GROUP_DOCS_CONTRACT,
        ]
    )
    assert diagnostic_exit == 0

    diagnostic_latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert diagnostic_latest == aggregate_latest


def test_local_ci_parity_production_mode_missing_docker_cli_mentions_canonical_command(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()

    def _fake_run_command(command, *, cwd):
        del command, cwd
        return subprocess.CompletedProcess(["ok"], 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module, "run_command", _fake_run_command)
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        module,
        "run_required_documentation_validation",
        lambda repo_root: [],
    )

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--mode",
            "production",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert (
        "Docker CLI is required for blocking Docker image build parity" in captured.out
    )
    assert "--mode production" in captured.out
    assert "--include-docker-build" in captured.out


def test_local_ci_parity_reports_missing_dev_dependencies_before_quality_steps(
    monkeypatch,
    tmp_path: Path,
    capsys,
):
    module = _load_local_ci_parity_module()
    executed_commands: list[tuple[str, ...]] = []

    def _fake_run_command(command, *, cwd):
        del cwd
        command_tuple = tuple(command)
        executed_commands.append(command_tuple)

        if any("find_spec" in part for part in command_tuple):
            return subprocess.CompletedProcess(
                list(command_tuple),
                1,
                stdout='["black", "pytest"]\n',
                stderr="",
            )

        return subprocess.CompletedProcess(
            list(command_tuple),
            0,
            stdout="ok\n",
            stderr="",
        )

    monkeypatch.setattr(module, "run_command", _fake_run_command)

    exit_code = module.main(
        [
            "--repo-root",
            str(tmp_path),
            "--base-rev",
            "base-sha",
            "--skip-integration",
            "--skip-pr-template-check",
        ]
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[ERROR] Python environment preflight" in captured.out
    assert "development/test modules: black, pytest" in captured.out
    assert "Run `./setup.sh`" in captured.out
    assert "Skipping Python quality/test steps" in captured.out
    assert "[ERROR] Black format check" not in captured.out
    assert "[ERROR] Pytest suite (tests/)" not in captured.out
    assert not any(command[1:3] == ("-m", "black") for command in executed_commands)
    assert not any(command[1:3] == ("-m", "pytest") for command in executed_commands)
