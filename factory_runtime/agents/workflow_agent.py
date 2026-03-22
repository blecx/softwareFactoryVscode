#!/usr/bin/env python3
"""
workflow_agent.py - 6-Phase Workflow Agent (Orchestrator)

Executes the standard 6-phase issue resolution workflow:
1. Context Gathering  2. Planning  3. Implementation
4. Testing  5. Review  6. PR & Merge

Supporting classes are split into:
- workflow_state.py          CrossRepoContext
- workflow_error_recovery.py SmartRetry, ParallelValidator, ErrorRecovery
- workflow_phase_helpers.py  IncrementalKnowledgeBase, SmartValidation,
                             IssuePreflight, DocUpdater
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from factory_runtime.agents.base_agent import AgentPhase, BaseAgent  # noqa: E402
from factory_runtime.agents.workflow_error_recovery import (  # noqa: E402
    ErrorRecovery,
    ParallelValidator,
    SmartRetry,
)
from factory_runtime.agents.workflow_phase_helpers import (  # noqa: E402
    DocUpdater,
    IncrementalKnowledgeBase,
    IssuePreflight,
    SmartValidation,
)
from factory_runtime.agents.workflow_phase_services import (  # noqa: E402
    WorkflowPhaseService,
    build_default_phase_services,
)
from factory_runtime.agents.workflow_side_effect_adapters import (  # noqa: E402
    CommandExecutionResult,
    SubprocessWorkflowSideEffectAdapter,
    WorkflowSideEffectAdapter,
    WorkflowSideEffectError,
)
from factory_runtime.agents.workflow_state import CrossRepoContext  # noqa: E402


class WorkflowAgent(BaseAgent):
    """Agent that follows the 6-phase workflow from successful issue completions."""

    def __init__(self, kb_dir: Path = Path("agents/knowledge")):
        super().__init__(name="workflow_agent", version="1.0.0", kb_dir=kb_dir)

        self.side_effects: WorkflowSideEffectAdapter = (
            SubprocessWorkflowSideEffectAdapter()
        )

        self.phases = [
            AgentPhase("Phase 1: Context", "Read issue and gather context"),
            AgentPhase("Phase 2: Planning", "Create planning document"),
            AgentPhase(
                "Phase 3: Implementation", "Implement changes with test-first approach"
            ),
            AgentPhase("Phase 4: Testing", "Build and test changes"),
            AgentPhase("Phase 5: Review", "Self-review and Copilot review"),
            AgentPhase("Phase 6: PR & Merge", "Create PR and merge"),
        ]

        # Phase 1 helpers (Issues #159-#163)
        self.cross_repo_context = CrossRepoContext(side_effects=self.side_effects)
        self.smart_retry = SmartRetry(side_effects=self.side_effects)
        self.parallel_validator = ParallelValidator()

        # Phase 2 helpers (Issues #164-#168)
        self.incremental_kb = IncrementalKnowledgeBase(kb_dir=kb_dir)
        self.smart_validation = SmartValidation(side_effects=self.side_effects)
        self.error_recovery = ErrorRecovery(side_effects=self.side_effects)
        self.issue_preflight = IssuePreflight(side_effects=self.side_effects)
        self.doc_updater = DocUpdater(side_effects=self.side_effects)

        # Phase service interfaces (Issue #273)
        self.phase_services: Dict[str, WorkflowPhaseService] = (
            build_default_phase_services()
        )

        self.ci_behavior_knowledge = self._load_ci_behavior_knowledge()
        self.interactive = False

    # ------------------------------------------------------------------ #
    # Execution entry points                                               #
    # ------------------------------------------------------------------ #

    def execute(self, issue_num: int, **kwargs) -> bool:
        """Execute the complete 6-phase workflow."""
        self._validate_issue_number(issue_num)
        self.interactive = bool(kwargs.get("interactive", False))

        self.log(f"🎯 Executing workflow for Issue #{issue_num}", "info")
        principles = self._load_principles()
        self.log(f"Loaded {len(principles)} guiding principles", "info")

        for phase in self.phases:
            success = self._execute_phase(phase, issue_num)
            if not success and not phase.skipped:
                self.log(f"Phase failed: {phase.name}", "error")
                return False

        self._display_summary()
        return all(p.completed or p.skipped for p in self.phases)

    # ------------------------------------------------------------------ #
    # Phase execution                                                      #
    # ------------------------------------------------------------------ #

    def _execute_phase(self, phase: AgentPhase, issue_num: int) -> bool:
        """Execute a single phase, updating KB before and after."""
        self.log(f"\n{'=' * 60}", "info")
        self.log(f"{phase.name}: {phase.description}", "info")
        self.log(f"{'=' * 60}", "info")

        phase.start()

        learnings = self.incremental_kb.get_relevant_learnings(
            phase.name, {"issue_num": issue_num}
        )
        if learnings:
            self.log(f"📚 Found {len(learnings)} relevant learnings from KB", "info")
            for x in learnings[:3]:
                desc = x.get("error", x.get("description", "N/A"))[:80]
                self.log(f"  • {x.get('type', 'unknown')}: {desc}", "info")

        try:
            phase_output: Dict = {}
            service = self._get_phase_service(phase.name)

            if not service:
                success = False
            else:
                execution_result = service.execute(self, issue_num)
                success = execution_result.success
                phase_output = execution_result.output

            if success:
                phase.complete()
                self.log(
                    f"✅ {phase.name} completed in {phase.duration_minutes():.1f} minutes",
                    "success",
                )
            else:
                phase.fail("Phase execution returned False")
                phase_output["error"] = "Phase execution returned False"

            extracted = self.incremental_kb.extract_learnings_from_phase(
                phase.name, phase_output, success
            )
            if extracted:
                self.incremental_kb.update_kb_after_phase(phase.name, extracted)
                self.log(f"💾 Saved {len(extracted)} learnings to KB", "info")

            return success

        except Exception as e:
            phase.fail(str(e))
            self.log(f"❌ {phase.name} failed: {e}", "error")
            extracted = self.incremental_kb.extract_learnings_from_phase(
                phase.name, {"error": str(e), "context": phase.name}, False
            )
            if extracted:
                self.incremental_kb.update_kb_after_phase(phase.name, extracted)
            return False

    # ------------------------------------------------------------------ #
    # Validation helpers                                                   #
    # ------------------------------------------------------------------ #

    def run_command(
        self, command: str, description: Optional[str] = None, check: bool = True
    ) -> CommandExecutionResult:
        """Run command via workflow side-effect adapter."""
        if description:
            self.log(description, "progress")
        self.log(f"Command: {command}", "info")

        if self.dry_run:
            self.log("(Dry run - command not executed)", "info")
            return CommandExecutionResult(returncode=0, stdout="", stderr="")

        try:
            result = self.side_effects.run(command, shell=True, check=check)
            if result.stdout:
                self.log(f"Output: {result.stdout.strip()}", "info")
            return result
        except WorkflowSideEffectError as exc:
            self.log(f"Command failed: {exc}", "error")
            if exc.stderr:
                self.log(f"Error: {exc.stderr.strip()}", "error")
            if check:
                raise
            return CommandExecutionResult(
                returncode=exc.returncode or 1,
                stdout="",
                stderr=exc.stderr or str(exc),
            )

    def validate_pr_template(self, pr_body_file: Path) -> bool:
        """Validate PR template before creation (Issue #159)."""
        validate_script = Path("scripts/validate-pr-template.sh")
        if not validate_script.exists():
            self.log("PR template validation script not found, skipping", "warning")
            return True

        repo_type = (
            "client" if self.cross_repo_context.current_repo == "client" else "backend"
        )
        result = self.run_command(
            f"{validate_script} --body-file {pr_body_file} --repo {repo_type}",
            "Validating PR template",
            check=False,
        )
        return result.returncode == 0

    def run_parallel_validations(self, commands: List[str]) -> bool:
        """Run validation commands in parallel (Issue #163)."""
        self.log("Running validations in parallel...", "progress")
        start_time = time.time()

        results = asyncio.run(
            self.parallel_validator.validate_pr_parallel(
                Path("."), commands, side_effects=self.side_effects
            )
        )

        elapsed = time.time() - start_time
        self.log(f"Parallel validation completed in {elapsed:.1f}s", "info")

        all_passed = True
        for cmd, (returncode, stdout, stderr) in results.items():
            if returncode != 0:
                self.log(f"❌ {cmd} failed", "error")
                if stderr:
                    print(stderr)
                all_passed = False
            else:
                self.log(f"✅ {cmd} passed", "success")

        return all_passed

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _validate_issue_number(self, issue_num: int) -> None:
        if not isinstance(issue_num, int):
            raise ValueError(f"Issue number must be an integer, got {type(issue_num)}")
        if issue_num < self.MIN_ISSUE_NUMBER or issue_num > self.MAX_ISSUE_NUMBER:
            raise ValueError(
                f"Issue number must be between {self.MIN_ISSUE_NUMBER} and {self.MAX_ISSUE_NUMBER}"
            )

    def _get_phase_service(self, phase_name: str) -> Optional[WorkflowPhaseService]:
        for phase_key, service in self.phase_services.items():
            if phase_key in phase_name:
                return service
        return None

    def _load_principles(self) -> List[str]:
        return [
            "No hallucinations - verify everything",
            "Complete all 6 phases",
            "Test-first approach",
            "Get approval before removing functionality",
        ]

    def _load_ci_behavior_knowledge(self) -> Dict:
        ci_kb_path = self.kb_dir / "ci_workflows_behavior.json"
        if ci_kb_path.exists():
            try:
                import json

                with open(ci_kb_path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _extract_pr_number(self, gh_output: str) -> Optional[int]:
        import re

        match = re.search(r"/pull/(\d+)", gh_output)
        return int(match.group(1)) if match else None

    def _display_summary(self):
        self.log("\n" + "=" * 60, "info")
        self.log("WORKFLOW SUMMARY", "info")
        self.log("=" * 60, "info")
        for phase in self.phases:
            self.log(str(phase), "info")
        total_time = sum(p.duration_minutes() for p in self.phases)
        self.log(
            f"\n📊 Total time: {total_time:.1f} minutes ({total_time / 60:.1f} hours)",
            "info",
        )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="6-Phase Workflow Agent for Issue Resolution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Run workflow for Issue #26:
    ./agents/workflow_agent.py --issue 26

  Dry run (no actual commands):
    ./agents/workflow_agent.py --issue 26 --dry-run
        """,
    )
    parser.add_argument(
        "--issue", type=int, required=True, help="Issue number to process"
    )
    parser.add_argument("--dry-run", action="store_true", help="No actual commands")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Enable guided prompt pauses between phases.",
    )
    parser.add_argument(
        "--kb-dir",
        type=str,
        default="agents/knowledge",
        help="Knowledge base directory",
    )

    args = parser.parse_args()
    agent = WorkflowAgent(kb_dir=Path(args.kb_dir))
    success = agent.run(
        dry_run=args.dry_run,
        issue_num=args.issue,
        interactive=args.interactive,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
