"""
Adapter to wrap MAESTRO inside the v1 AutonomousWorkflowAgent interface.
This bridges `scripts/work-issue.py` to `agents/maestro.py`.
"""

from pathlib import Path
from typing import Optional

from factory_runtime.agents.maestro import MaestroOrchestrator


class MaestroAdapter:
    """Provides a compatible interface for older work-issue scripts using MAESTRO."""

    def __init__(self, issue_number: int, dry_run: bool = False, **kwargs):
        self.issue_number = issue_number
        self.dry_run = dry_run
        self.plan_only = False
        self.system_instructions = ""

    async def initialize(self) -> None:
        """Mock initialize."""
        self.system_instructions = self._build_system_instructions()

    def _build_system_instructions(self) -> str:
        """Mock instructions builder."""
        return ""

    async def execute(self, issue_summary: str = "", pr_title: str = "") -> bool:
        """Run MAESTRO for this issue."""
        if self.dry_run:
            print(f"MAESTRO Adapter: Dry run for issue #{self.issue_number}")
            return True

        if self.plan_only:
            print(f"MAESTRO Adapter: plan_only is not fully supported yet.")

        # Injects any specific instructions into the issue body if needed
        full_body = issue_summary
        if self.system_instructions:
            full_body = f"{issue_summary}\n\n[Agent Instructions Override]\n{self.system_instructions}"

        orq = MaestroOrchestrator(workspace_root=Path.cwd())

        # Determine repo (could be passed in, currently defaults to YOUR_ORG/YOUR_REPO)
        # Using a fixed default here for compatibility, can be extracted from env.
        repo = "YOUR_ORG/YOUR_REPO"

        result = await orq.run_issue(
            issue_number=self.issue_number,
            repo=repo,
            issue_title=pr_title,
            issue_body=full_body,
        )
        return result.success

    async def continue_conversation(self, user_input: str) -> str:
        return "Interactive conversation is not fully supported by MAESTRO adapter."
