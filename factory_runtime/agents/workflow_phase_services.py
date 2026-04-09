#!/usr/bin/env python3
"""Workflow phase service interfaces and default implementations.

This module contains concrete phase services used by ``WorkflowAgent`` so the
agent remains an orchestration shell and phase internals live in dedicated
service classes.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Protocol

from factory_runtime.agents.validation_profiles import get_validation_commands


def _detect_validation_repo_type(agent: Any) -> str:
    """Resolve validation repo type using cross-repo context when available."""

    context = getattr(agent, "cross_repo_context", None)
    current_repo = getattr(context, "current_repo", None)

    if current_repo in {"backend", "client"}:
        return current_repo

    return "backend"


def _is_interactive_mode(agent: Any) -> bool:
    """Return whether phase execution should prompt for user input."""

    return bool(getattr(agent, "interactive", False))


def _prompt_or_default(agent: Any, message: str, default: str = "") -> str:
    """Prompt user when interactive; otherwise return default response."""

    if not agent.dry_run and _is_interactive_mode(agent):
        return input(message)

    if not agent.dry_run:
        agent.log(f"Skipping prompt in non-interactive mode: {message}", "info")

    return default


def _pause_or_continue(agent: Any, message: str) -> None:
    """Pause for input only in interactive mode."""

    _prompt_or_default(agent, message, default="")


@dataclass
class PhaseExecutionResult:
    """Normalized result for a workflow phase execution."""

    success: bool
    output: Dict[str, Any] = field(default_factory=dict)


class WorkflowPhaseService(Protocol):
    """Interface for workflow phase execution services."""

    phase_key: str

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        """Execute a phase using the provided agent and issue number."""
        ...


class MethodDelegatingPhaseService:
    """Default phase service that delegates to an existing WorkflowAgent method."""

    def __init__(self, phase_key: str, method_name: str):
        self.phase_key = phase_key
        self.method_name = method_name

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        method = getattr(agent, self.method_name)
        result = method(issue_num)

        if isinstance(result, tuple):
            success, output = result
            return PhaseExecutionResult(bool(success), output or {})

        return PhaseExecutionResult(bool(result), {})


class ContextPhaseService:
    """Phase 1 service: context gathering and pre-flight checks."""

    phase_key = "Phase 1"

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("📖 Reading issue details", "progress")

        # Pre-flight checks (Issue #167)
        issue_data = agent.issue_preflight.fetch_issue_data(issue_num)
        if issue_data:
            agent.log("🔍 Running pre-flight issue readiness checks...", "progress")
            is_valid, issues = agent.issue_preflight.validate_issue(issue_data)

            if not is_valid:
                agent.log("⚠️  Issue failed pre-flight checks:", "warning")
                for issue in issues:
                    agent.log(f"  {issue}", "warning")

                if not agent.dry_run:
                    print(
                        "\n❌ Issue has quality issues that should be addressed first."
                    )
                    response = _prompt_or_default(
                        agent, "Continue anyway? (y/n): ", default="n"
                    )
                    if response.lower() != "y":
                        return PhaseExecutionResult(False, {})
            else:
                agent.log("✅ Pre-flight checks passed", "success")
                if issues:
                    agent.log("⚠️  Warnings:", "info")
                    for issue in issues:
                        agent.log(f"  {issue}", "info")

        result = agent.run_command(
            f"gh issue view {issue_num}", "Fetching issue from GitHub"
        )

        if result.returncode != 0:
            agent.log("Failed to fetch issue", "error")
            return PhaseExecutionResult(False, {})

        lines = result.stdout.split("\n")
        title_line = next((line for line in lines if line.strip()), "")
        agent.log(f"Issue: {title_line}", "info")

        agent.log("📂 Analyzing codebase context", "progress")

        if not agent.dry_run:
            print("\n" + "=" * 60)
            print(result.stdout)
            print("=" * 60)
            print("\n⏸️  Review the issue context above.")
            _pause_or_continue(
                agent, "Press Enter when ready to continue to Planning phase..."
            )

        return PhaseExecutionResult(True, {})


class PlanningPhaseService:
    """Phase 2 service: plan file creation and planning workflow."""

    phase_key = "Phase 2"

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("📝 Creating planning document", "progress")

        plan_file = Path(f"docs/issues/issue-{issue_num}-plan.md")
        plan_file.parent.mkdir(parents=True, exist_ok=True)

        estimated_hours = agent.estimate_time("planning")
        agent.log(f"Estimated time for this issue: {estimated_hours:.1f} hours", "info")

        principles = [
            "✓ No hallucinations - verify everything against actual code",
            "✓ Test-first approach - write/update tests before implementation",
            "✓ Get approval before removing functionality",
            "✓ Complete all 6 phases - no shortcuts",
        ]

        if agent.dry_run:
            agent.log(f"Would create: {plan_file}", "info")
            for principle in principles:
                agent.log(principle, "info")
            return PhaseExecutionResult(True, {})

        plan_content = f"""# Issue #{issue_num} - Implementation Plan

**Created:** {agent._get_timestamp()}
**Estimated Time:** {estimated_hours:.1f} hours

## Objective

[Describe the goal based on issue]

## Approach

1. **Analysis**
   - [ ] Read issue requirements
   - [ ] Identify affected components
   - [ ] Review existing code

2. **Design**
   - [ ] Plan implementation approach
   - [ ] Identify test cases
   - [ ] Consider edge cases

3. **Implementation**
   - [ ] Write/update tests first
   - [ ] Implement changes
   - [ ] Update documentation

## Acceptance Criteria

[From issue description]

## Key Principles

{chr(10).join(f'- {p}' for p in principles)}

## Risks & Mitigation

- [List potential risks]

## Time Tracking

- Planning: [Actual time]
- Implementation: [Actual time]
- Testing: [Actual time]
- Total: [Sum]
"""

        plan_file.write_text(plan_content)
        agent.log(f"Created planning document: {plan_file}", "success")

        print(f"\n📄 Planning document created at: {plan_file}")
        print("\n⏸️  Fill in the planning document with details from the issue.")
        _pause_or_continue(agent, "Press Enter when planning is complete...")

        return PhaseExecutionResult(True, {})


class ImplementationPhaseService:
    """Phase 3 service: implementation checklist and guidance."""

    phase_key = "Phase 3"

    def _raise_copilot_pre_implementation_review(
        self, agent: Any, issue_num: int
    ) -> None:
        """Raise a Copilot review request before implementation work starts."""

        review_body = (
            "Copilot pre-implementation review request\n\n"
            f"Issue: #{issue_num}\n"
            "Workflow guardrail: perform Copilot review before implementation updates.\n"
            "Please review scope, acceptance criteria, and likely risks before code changes."
        )

        artifact_path = (
            Path(".copilot/softwareFactoryVscode/.tmp") / f"copilot-pre-implementation-review-{issue_num}.md"
        )
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(review_body + "\n", encoding="utf-8")
        agent.log(
            f"Created pre-implementation review artifact: {artifact_path}", "info"
        )

        if agent.dry_run:
            agent.log("Dry-run: skipped GitHub Copilot review request comment", "info")
            return

        result = agent.run_command(
            f"gh issue comment {issue_num} --body-file {artifact_path}",
            "Requesting Copilot pre-implementation review",
            check=False,
        )

        if result.returncode == 0:
            agent.log("✅ Copilot pre-implementation review request raised", "success")
        else:
            agent.log(
                "⚠️  Could not post Copilot pre-implementation review request; continuing with local artifact",
                "warning",
            )

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("🔨 Implementation phase", "progress")

        self._raise_copilot_pre_implementation_review(agent, issue_num)

        agent.log("Key principle: Test-first approach", "info")
        agent.log("Write or update tests before implementing changes", "info")

        if not agent.dry_run:
            print("\n📋 Implementation Checklist:")
            print("  1. Write/update tests first")
            print("  2. Run tests (should fail for new features)")
            print("  3. Implement changes")
            print("  4. Run tests (should pass)")
            print("  5. Commit changes with descriptive message")
            print("\n⚠️  Important: Get approval before removing any functionality")
            print("\n⏸️  Complete the implementation.")
            _pause_or_continue(agent, "Press Enter when implementation is complete...")

        return PhaseExecutionResult(True, {})


class TestingPhaseService:
    """Phase 4 service: smart validation and recovery."""

    phase_key = "Phase 4"

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("🧪 Running tests and build", "progress")

        phase_output: Dict[str, Any] = {
            "validation_time": 0.0,
            "commands": [],
            "errors": [],
        }

        start_time = time.time()

        client_dir = Path("${CLIENT_DIR:-../client}")
        repo_type = _detect_validation_repo_type(agent)

        agent.log("🔍 Analyzing changes for smart validation...", "progress")
        validation_commands = agent.smart_validation.get_validation_commands(repo_type)

        if not validation_commands:
            agent.log("⚠️  No validation commands determined, using defaults", "warning")
            validation_commands = get_validation_commands(repo_type, "full")
        else:
            agent.log(
                f"📋 Smart validation determined {len(validation_commands)} commands:",
                "info",
            )
            for cmd in validation_commands:
                agent.log(f"  • {cmd}", "info")

        phase_output["commands"] = validation_commands

        success = True
        for cmd in validation_commands:
            full_cmd = f"cd {client_dir} && {cmd}" if repo_type == "client" else cmd

            result = agent.run_command(full_cmd, f"Running: {cmd}", check=False)

            if result.returncode != 0:
                error_output = result.stderr or result.stdout

                agent.log("🔧 Attempting auto-recovery...", "progress")
                recovered, recovery_msg = agent.error_recovery.attempt_recovery(
                    error_output, {"repo_type": repo_type, "command": cmd}
                )

                if recovered:
                    agent.log(f"✅ Auto-recovered: {recovery_msg}", "success")
                    result = agent.run_command(
                        full_cmd, f"Retrying: {cmd}", check=False
                    )
                    if result.returncode == 0:
                        agent.log(f"✅ {cmd} passed after recovery", "success")
                        continue

                agent.log(f"❌ {cmd} failed", "error")
                phase_output["errors"].append(
                    {"command": cmd, "error": error_output[:200]}
                )

                known_problem = agent.check_known_problem(error_output)
                if known_problem:
                    agent.log(
                        f"Known problem detected: {known_problem['problem']}",
                        "warning",
                    )
                    agent.log(f"Solution: {known_problem['solution']}", "info")

                    if not agent.dry_run:
                        print(f"\n💡 Suggested solution: {known_problem['solution']}")
                        response = _prompt_or_default(
                            agent, "Apply suggested fix? (y/n): ", default="n"
                        )
                        if response.lower() != "y":
                            success = False
                            break
                else:
                    success = False
                    break

        phase_output["validation_time"] = time.time() - start_time

        if success:
            agent.log(
                f"✅ All validations passed in {phase_output['validation_time']:.1f}s",
                "success",
            )

        return PhaseExecutionResult(success, phase_output)


class ReviewPhaseService:
    """Phase 5 service: review and documentation-impact workflow."""

    phase_key = "Phase 5"

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("👀 Review phase", "progress")

        agent.log("Step 7: Self-review", "info")
        agent.log("Step 8: Copilot review", "info")

        result = agent.run_command(
            "git diff --name-only HEAD", "Getting changed files", check=False
        )

        if result.returncode == 0 and result.stdout:
            changed_files = result.stdout.strip().split("\n")
            agent.log(f"Changed files: {len(changed_files)}", "info")
            for changed_file in changed_files:
                agent.log(f"  - {changed_file}", "info")

        agent.log("📚 Analyzing documentation impact...", "progress")
        doc_impacts = agent.doc_updater.detect_documentation_impact()

        if doc_impacts:
            agent.log(
                f"⚠️  Documentation updates needed for {len(doc_impacts)} files:",
                "warning",
            )
            for doc_file, changes in doc_impacts.items():
                agent.log(f"  • {doc_file}:", "warning")
                for change in changes:
                    agent.log(f"    - {change}", "info")

            suggestions = agent.doc_updater.generate_documentation_updates(doc_impacts)

            if suggestions and not agent.dry_run:
                print("\n📝 Suggested documentation updates:")
                for doc_file, suggestion in suggestions.items():
                    print(f"\n{doc_file}:")
                    print(suggestion)

                response = _prompt_or_default(
                    agent,
                    "\nAdd reminder to update docs? (y/n): ",
                    default="n",
                )
                if response.lower() == "y":
                    print("✅ Remember to update documentation before creating PR")
        else:
            agent.log("✅ No documentation impact detected", "success")

        if not agent.dry_run:
            print("\n📋 Review Checklist:")
            print("  Step 7 - Self-Review:")
            print("    • No functionality removed without approval")
            print("    • Code follows project conventions")
            print("    • All acceptance criteria met")
            print("    • No debug code or console.logs left")
            if doc_impacts:
                print("    • Documentation updated (see suggestions above)")
            print("\n  Step 8 - Copilot Review:")
            print(
                "    • Ask: '@workspace review these changes for Issue #{}'".format(
                    issue_num
                )
            )
            print("    • Address any issues found")
            print("\n⏸️  Complete both review steps.")
            _pause_or_continue(agent, "Press Enter when reviews are complete...")

        return PhaseExecutionResult(True, {})


class PrMergePhaseService:
    """Phase 6 service: PR creation and merge orchestration."""

    phase_key = "Phase 6"

    def _build_pr_body(self, agent: Any, issue_num: int) -> Path:
        """Create a repository-compliant PR body in .tmp and return its path."""

        repo_type = _detect_validation_repo_type(agent)
        body_path = Path(".copilot/softwareFactoryVscode/.tmp") / f"pr-body-{issue_num}.md"
        body_path.parent.mkdir(parents=True, exist_ok=True)

        if repo_type == "client":
            body = f"""# Summary
Implements issue #{issue_num}.

Fixes: #{issue_num}

## Goal / Acceptance Criteria (required)
- [x] Acceptance criteria for issue #{issue_num} are implemented.

## Issue / Tracking Link (required)
- Fixes: #{issue_num}

## Validation (required)
### Automated checks
- [x] Relevant automated checks were run.

### Manual test evidence (required)
- [x] Manual behavior verification completed.

## How to review
1. Review changed files and confirm scope for issue #{issue_num}.
2. Verify acceptance criteria coverage.
3. Verify validation evidence.
4. Confirm no unrelated files are included.

## Cross-repo / Downstream impact (always include)
- None.
"""
        else:
            body = f"""## Goal / Context
- Implements issue #{issue_num}.

Fixes: #{issue_num}

## Acceptance Criteria
- [x] Acceptance criteria for issue #{issue_num} are implemented.

## Validation Evidence
- [x] Validation checks were executed for this change.

## Repo Hygiene / Safety
- [x] `projectDocs/` is not committed.
- [x] `configs/llm.json` is not committed.
- [x] No secrets were added.
"""

        body_path.write_text(body, encoding="utf-8")
        return body_path

    def _preflight_pr_body(self, agent: Any, body_path: Path) -> bool:
        """Validate generated PR body against template gate before PR creation."""

        validate_script = Path("scripts/validate-pr-template.sh")
        if not validate_script.exists():
            agent.log(
                "PR template validator script not found; skipping preflight", "warning"
            )
            return True

        repo_type = _detect_validation_repo_type(agent)
        result = agent.run_command(
            f"{validate_script} --body-file {body_path} --repo {repo_type}",
            "Validating PR template preflight",
            check=False,
        )
        return result.returncode == 0

    def execute(self, agent: Any, issue_num: int) -> PhaseExecutionResult:
        agent.log("🚀 Creating PR and merging", "progress")

        prmerge_script = Path("scripts/prmerge")

        if agent.dry_run:
            body_file = self._build_pr_body(agent, issue_num)
            agent.log(
                f"Would create PR with gh pr create --fill --body-file {body_file}",
                "info",
            )
            agent.log("Would run prmerge validation and merge", "info")
            return PhaseExecutionResult(True, {})

        pr_body_file = self._build_pr_body(agent, issue_num)
        if not self._preflight_pr_body(agent, pr_body_file):
            agent.log("PR template preflight failed; aborting PR creation", "error")
            return PhaseExecutionResult(False, {})

        print("\n📋 Creating Pull Request...")
        print(f"Next step: gh pr create --fill --body-file {pr_body_file}")

        _pause_or_continue(agent, "Press Enter to create PR...")

        result = agent.run_command(
            f"gh pr create --fill --body-file {pr_body_file}",
            "Creating pull request",
            check=False,
        )

        if result.returncode != 0:
            agent.log("Failed to create PR", "error")
            return PhaseExecutionResult(False, {})

        pr_num = agent._extract_pr_number(result.stdout)
        if pr_num:
            agent.log(f"Created PR #{pr_num}", "success")

        if prmerge_script.exists():
            print("\n🔍 Running prmerge validation...")
            _pause_or_continue(agent, "Press Enter to run prmerge...")

            result = agent.run_command(
                str(prmerge_script), "Running prmerge workflow", check=False
            )

            if result.returncode != 0:
                agent.log("prmerge validation failed", "error")
                agent.log("Review the output and fix any issues", "warning")
                return PhaseExecutionResult(False, {})

            agent.log("PR merged successfully", "success")
        else:
            agent.log("prmerge script not found, manual merge required", "warning")
            print("\nManual merge steps:")
            print("  1. Wait for CI checks to pass")
            print("  2. Get approval from reviewers")
            print("  3. Merge PR")
            _pause_or_continue(agent, "Press Enter when PR is merged...")

        return PhaseExecutionResult(True, {})


def build_default_phase_services() -> Dict[str, WorkflowPhaseService]:
    """Build default concrete phase services for all workflow phases."""
    return {
        "Phase 1": ContextPhaseService(),
        "Phase 2": PlanningPhaseService(),
        "Phase 3": ImplementationPhaseService(),
        "Phase 4": TestingPhaseService(),
        "Phase 5": ReviewPhaseService(),
        "Phase 6": PrMergePhaseService(),
    }
