#!/usr/bin/env python3
"""
base_agent.py - Base class for all AI agents

This module provides the foundation for custom AI agents trained on
chat exports and project knowledge.
"""

import json
import subprocess
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union

from agents.tooling.gh_throttle import run_gh_throttled


class BaseAgent(ABC):
    """Base class for all custom AI agents."""

    # Constants for validation
    MIN_ISSUE_NUMBER = 1
    MAX_ISSUE_NUMBER = 99999

    def __init__(
        self, name: str, version: str, kb_dir: Path = Path("agents/knowledge")
    ):
        if not name or not name.strip():
            raise ValueError("Agent name cannot be empty")
        if not version or not version.strip():
            raise ValueError("Agent version cannot be empty")

        self.name = name
        self.version = version
        self.kb_dir = kb_dir
        self.knowledge_base = self._load_knowledge_base()
        self.run_log = []
        self.dry_run = False

    def _load_knowledge_base(self) -> Dict:
        """Load relevant knowledge base files."""
        kb = {}

        kb_files = [
            "workflow_patterns.json",
            "problem_solutions.json",
            "time_estimates.json",
            "command_sequences.json",
            "agent_metrics.json",
        ]

        for filename in kb_files:
            filepath = self.kb_dir / filename
            if filepath.exists():
                with open(filepath) as f:
                    kb[filename.replace(".json", "")] = json.load(f)

        return kb

    def log(self, message: str, level: str = "info"):
        """Log a message with timestamp."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        icons = {
            "info": "ℹ️ ",
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌",
            "progress": "🔄",
        }
        icon = icons.get(level, "")

        log_entry = {"timestamp": timestamp, "level": level, "message": message}
        self.run_log.append(log_entry)

        print(f"{icon} [{timestamp}] {message}")

    def run_command(
        self, command: str, description: Optional[str] = None, check: bool = True
    ) -> Union[subprocess.CompletedProcess, subprocess.CalledProcessError]:
        """Run a shell command with logging.

        Args:
            command: Shell command to execute
            description: Optional description for logging
            check: If True, raise exception on non-zero exit code

        Returns:
            CompletedProcess on success, CalledProcessError if check=False and command fails

        Raises:
            CalledProcessError: If check=True and command fails
        """
        if description:
            self.log(description, "progress")

        self.log(f"Command: {command}", "info")

        if self.dry_run:
            self.log("(Dry run - command not executed)", "info")
            return subprocess.CompletedProcess(command, 0, "", "")

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, check=check
            )

            if result.stdout:
                self.log(f"Output: {result.stdout.strip()}", "info")

            return result

        except subprocess.CalledProcessError as e:
            self.log(f"Command failed: {e}", "error")
            if e.stderr:
                self.log(f"Error: {e.stderr.strip()}", "error")

            if check:
                raise

            return e

    def check_known_problem(self, error_text: str) -> Optional[Dict]:
        """Check if error matches a known problem.

        Args:
            error_text: Error message to check against knowledge base

        Returns:
            Problem dict with 'problem' and 'solution' keys if found, None otherwise
        """
        problems = self.knowledge_base.get("problem_solutions", {}).get("problems", [])

        for problem in problems:
            # Simple substring match - could be improved with fuzzy matching
            if problem["problem"].lower() in error_text.lower():
                return problem

        return None

    def estimate_time(self, phase: str) -> float:
        """Estimate time for a phase based on historical data.

        Args:
            phase: Phase name to estimate time for

        Returns:
            Estimated time in minutes
        """
        phase_times = self.knowledge_base.get("time_estimates", {}).get(
            "phase_averages", {}
        )
        base_time = phase_times.get(phase.lower(), 1.0)

        # Apply multiplier
        multiplier = (
            self.knowledge_base.get("time_estimates", {})
            .get("statistics", {})
            .get("avg_multiplier", 1.0)
        )

        return base_time * multiplier

    def get_command_sequence(self, category: str) -> List[str]:
        """Get reusable commands for a category.

        Args:
            category: Command category (e.g., 'git', 'test', 'build')

        Returns:
            List of commands for the category, empty list if not found
        """
        sequences = self.knowledge_base.get("command_sequences", {}).get(
            "reusable_commands", {}
        )
        return sequences.get(category, [])

    def validate_prerequisites(self) -> bool:
        """Validate that all prerequisites are met.

        Returns:
            True if all prerequisites are satisfied, False otherwise
        """
        # Check git repository
        if not Path(".git").exists():
            self.log("Not in a git repository", "error")
            return False

        # Check GitHub CLI
        try:
            run_gh_throttled(
                ["gh", "--version"],
                capture_output=True,
                check=True,
                min_interval_seconds=0,
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log("GitHub CLI (gh) not installed", "error")
            return False

        return True

    def save_run_log(self, issue_num: int):
        """Save run log for analysis.

        Args:
            issue_num: Issue number for log file naming

        Raises:
            ValueError: If issue number is invalid
        """
        if (
            not isinstance(issue_num, int)
            or issue_num < self.MIN_ISSUE_NUMBER
            or issue_num > self.MAX_ISSUE_NUMBER
        ):
            raise ValueError(
                f"Issue number must be an integer between {self.MIN_ISSUE_NUMBER} and {self.MAX_ISSUE_NUMBER}"
            )

        log_dir = self.kb_dir.parent / "training" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = (
            log_dir
            / f"issue-{issue_num}-{self.name}-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        )

        run_data = {
            "agent": self.name,
            "version": self.version,
            "issue_num": issue_num,
            "start_time": self.run_log[0]["timestamp"] if self.run_log else None,
            "end_time": self.run_log[-1]["timestamp"] if self.run_log else None,
            "total_entries": len(self.run_log),
            "log": self.run_log,
        }

        with open(log_file, "w") as f:
            json.dump(run_data, f, indent=2)

        self.log(f"Run log saved to {log_file}", "success")

    @abstractmethod
    def execute(self, **kwargs) -> bool:
        """Execute the agent's main workflow.

        Must be implemented by subclasses.

        Args:
            **kwargs: Agent-specific parameters

        Returns:
            True if execution succeeded, False otherwise
        """
        pass

    def run(self, dry_run: bool = False, **kwargs) -> bool:
        """Main entry point for running the agent."""
        self.dry_run = dry_run

        if dry_run:
            self.log(f"Starting {self.name} v{self.version} (DRY RUN)", "info")
        else:
            self.log(f"Starting {self.name} v{self.version}", "info")

        # Validate prerequisites
        if not self.validate_prerequisites():
            self.log("Prerequisites check failed", "error")
            return False

        # Execute agent workflow
        try:
            success = self.execute(**kwargs)

            if success:
                self.log("Agent execution completed successfully", "success")
            else:
                self.log("Agent execution completed with issues", "warning")

            # Save log if issue number provided
            if "issue_num" in kwargs:
                self.save_run_log(kwargs["issue_num"])

            return success

        except KeyboardInterrupt:
            self.log("Agent execution interrupted by user", "warning")
            return False
        except Exception as e:
            self.log(f"Agent execution failed: {e}", "error")
            import traceback

            traceback.print_exc()
            return False


class AgentPhase:
    """Represents a single phase in an agent's workflow."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.start_time = None
        self.end_time = None
        self.completed = False
        self.skipped = False
        self.error = None

    def start(self):
        """Mark phase as started."""
        self.start_time = datetime.now()

    def complete(self):
        """Mark phase as completed."""
        self.end_time = datetime.now()
        self.completed = True

    def skip(self, reason: Optional[str] = None):
        """Mark phase as skipped."""
        self.skipped = True
        self.error = reason

    def fail(self, error: str):
        """Mark phase as failed."""
        self.end_time = datetime.now()
        self.error = error

    def duration_minutes(self) -> float:
        """Calculate phase duration in minutes."""
        if not self.start_time or not self.end_time:
            return 0.0

        delta = self.end_time - self.start_time
        return delta.total_seconds() / 60

    def __str__(self) -> str:
        """String representation."""
        if self.completed:
            return f"✅ {self.name} ({self.duration_minutes():.1f} min)"
        elif self.skipped:
            return f"⏭️  {self.name} (skipped)"
        elif self.error:
            return f"❌ {self.name} (failed: {self.error})"
        else:
            return f"⏳ {self.name} (in progress)"
