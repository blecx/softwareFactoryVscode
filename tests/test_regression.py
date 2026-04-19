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


def test_setup_repo_doc_matches_current_ci_checks():
    repo_root = Path(__file__).parent.parent
    setup_doc = (repo_root / "docs" / "setup-github-repository.md").read_text(
        encoding="utf-8"
    )

    assert "Python Code Quality (Lint & Format)" in setup_doc
    assert "Architectural Boundary Tests" in setup_doc
    assert "PR Template Conformance" in setup_doc


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

    assert "## Supported practical baseline (what this guide promises)" in install_doc
    assert ".copilot/softwareFactoryVscode/" in install_doc
    assert "software-factory.code-workspace" in install_doc
    assert "factory_stack.py preflight" in install_doc
    assert "factory_stack.py activate" in install_doc
    assert "verify_factory_install.py --target . --runtime" in install_doc
    assert (
        "verify_factory_install.py --target . --runtime --check-vscode-mcp"
        in install_doc
    )
    assert "`ADR-008` is accepted as the governing architecture" in install_doc
    assert "rollout remains open" in install_doc


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
    assert "accepted-but-still-open shared multi-tenant rollout program" in tests_readme
    assert "service-boundary isolation assertions" in tests_readme
    assert "`tests/test_throwaway_runtime_docker.py`" in tests_readme


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

    assert "software-factory.code-workspace" in handout
    assert "factory_stack.py preflight" in handout
    assert "factory_stack.py start --build" in handout
    assert "VS Code / Copilot CLI workflow" in handout
    assert "workspace.code-workspace" not in handout
    assert "automatically start the background task" not in handout

    assert "factory_stack.py activate" in cheat_sheet
    assert "factory_stack.py preflight" in cheat_sheet
    assert "refreshes generated runtime artifacts" in cheat_sheet
    assert "VS Code / Copilot CLI workflow" in cheat_sheet
    assert "shared_mode_status" in cheat_sheet
    assert "X-Workspace-ID" in cheat_sheet
    assert "PROJECT_WORKSPACE_ID" in cheat_sheet
    assert "stale registry data" not in cheat_sheet


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
    assert (
        "Shared multi-tenant promotion (ADR-008 accepted, rollout open)"
        in release_template
    )
    assert "Do not mark shared multi-tenant promotion as fulfilled" in release_template


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
        "The authoritative architectural definition of `active` lives in `ADR-009`"
        in architecture_doc
    )
    assert "activate` refreshes generated runtime artifacts" in architecture_doc

    assert (
        "Accepted runtime contracts now live in `ADR-012`, `ADR-007`, `ADR-008`, `ADR-009`, and `ADR-010`."
        in plan_doc
    )
    assert "maintained architecture synthesis" in plan_doc
    assert "Per `ADR-013`" in plan_doc
    assert (
        "the meaning of `installed`, `running`, and `active` comes from `ADR-009`"
        in plan_doc
    )


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

    assert "## Immediate Stabilization Rework Order" in plan_doc
    assert "## Execution Guardrails for This Rework" in plan_doc
    assert "## Mitigation Map and Current Resolution Status" in plan_doc
    assert "## Accepted ADR to Production Rollout Path" in plan_doc
    assert (
        "## Practical delivery split while shared-service rollout remains open"
        in plan_doc
    )
    assert re.search(
        r"\|\s*Scope\s*\|\s*Status\s*\|\s*Priority now\s*\|\s*Why it matters\s*\|",
        plan_doc,
    )
    assert "Rollout open" in plan_doc
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
    assert "### Shared multi-tenant rollout remains open" in plan_doc
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
    assert "Improvement plan" in captured.out
    assert "passed with 1 warning(s)" in captured.out


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
