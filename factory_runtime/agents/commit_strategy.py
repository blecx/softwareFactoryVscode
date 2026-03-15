"""
Multi-stage commit strategy for better Git history and code review.

This module implements a structured commit strategy that breaks down changes
into logical stages: tests, implementation, documentation, and refactoring.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
import subprocess


@dataclass
class CommitStage:
    """Represents a single commit stage with files and message."""

    name: str
    description: str
    file_patterns: List[str]
    files: List[str] = field(default_factory=list)
    commit_message_prefix: str = ""

    def matches_file(self, file_path: str) -> bool:
        """Check if a file matches this stage's patterns."""
        for pattern in self.file_patterns:
            if pattern in file_path:
                return True
        return False


@dataclass
class CommitMetrics:
    """Metrics for commit strategy performance."""

    commits_per_pr: int = 0
    pr_review_time_minutes: float = 0.0
    stages_completed: int = 0
    total_files_staged: int = 0


class CommitStrategy:
    """
    Multi-stage commit strategy for organizing changes into logical commits.

    Stages:
    1. Tests (red): Test files first
    2. Implementation (green): Core implementation files
    3. Documentation: README, docs, comments
    4. Refactoring: Cleanup and optimization

    Metrics tracked:
    - commits_per_pr: Number of commits in PR (target 2-4)
    - pr_review_time_minutes: Time to review PR
    - stages_completed: Number of stages executed
    - total_files_staged: Total files in all commits
    """

    def __init__(self, working_directory: Optional[str] = None):
        """
        Initialize commit strategy.

        Args:
            working_directory: Git repository directory (default: current dir)
        """
        self.working_directory = Path(working_directory or ".")
        self.metrics = CommitMetrics()

        # Define commit stages in order
        self.stages = [
            CommitStage(
                name="tests",
                description="Add/update tests (red phase)",
                file_patterns=["test_", "/tests/", "pytest", "spec.py"],
                commit_message_prefix="test:",
            ),
            CommitStage(
                name="implementation",
                description="Core implementation (green phase)",
                file_patterns=[".py", ".js", ".ts", ".java", ".go"],
                commit_message_prefix="feat:",
            ),
            CommitStage(
                name="documentation",
                description="Update documentation",
                file_patterns=["README", ".md", "docs/", "CHANGELOG"],
                commit_message_prefix="docs:",
            ),
            CommitStage(
                name="refactoring",
                description="Code cleanup and optimization",
                file_patterns=[".py", ".js", ".ts"],
                commit_message_prefix="refactor:",
            ),
        ]

    def get_changed_files(self) -> List[str]:
        """Get list of changed files in working directory."""
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(self.working_directory),
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]

    def get_staged_files(self) -> List[str]:
        """Get list of currently staged files."""
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=str(self.working_directory),
            capture_output=True,
            text=True,
            check=True,
        )
        return [f.strip() for f in result.stdout.splitlines() if f.strip()]

    def classify_files(self, files: List[str]) -> Dict[str, List[str]]:
        """
        Classify files into commit stages.

        Args:
            files: List of file paths to classify

        Returns:
            Dict mapping stage names to lists of files
        """
        classified = {stage.name: [] for stage in self.stages}

        for file_path in files:
            # Check which stage this file belongs to
            # Priority order: tests > docs > implementation > refactoring
            if any(pattern in file_path for pattern in self.stages[0].file_patterns):
                classified["tests"].append(file_path)
            elif any(pattern in file_path for pattern in self.stages[2].file_patterns):
                classified["documentation"].append(file_path)
            elif any(pattern in file_path for pattern in self.stages[1].file_patterns):
                # Only implementation if not test or doc
                if not any(pattern in file_path for pattern in ["test_", "/tests/"]):
                    classified["implementation"].append(file_path)

        return classified

    def create_stage_commit(
        self, stage_name: str, files: List[str], message: str, dry_run: bool = False
    ) -> bool:
        """
        Create a commit for a specific stage.

        Args:
            stage_name: Name of the stage
            files: Files to include in commit
            message: Commit message (prefix will be added)
            dry_run: If True, don't actually commit

        Returns:
            True if commit created successfully
        """
        if not files:
            return False

        # Find stage
        stage = next((s for s in self.stages if s.name == stage_name), None)
        if not stage:
            raise ValueError(f"Unknown stage: {stage_name}")

        # Build commit message with prefix
        full_message = f"{stage.commit_message_prefix} {message}\n\n{stage.description}"

        if dry_run:
            print(f"[DRY RUN] Would commit {len(files)} files for stage '{stage_name}'")
            print(f"  Message: {full_message}")
            print(f"  Files: {', '.join(files[:5])}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more")
            return True

        # Stage files
        for file_path in files:
            subprocess.run(
                ["git", "add", file_path], cwd=str(self.working_directory), check=True
            )

        # Create commit
        subprocess.run(
            ["git", "commit", "-m", full_message],
            cwd=str(self.working_directory),
            check=True,
        )

        # Update metrics
        self.metrics.commits_per_pr += 1
        self.metrics.stages_completed += 1
        self.metrics.total_files_staged += len(files)

        return True

    def execute_strategy(
        self, message_template: str = "Implement feature", dry_run: bool = False
    ) -> Dict[str, any]:
        """
        Execute multi-stage commit strategy on current changes.

        Args:
            message_template: Base message for commits
            dry_run: If True, show what would be committed without committing

        Returns:
            Dict with execution results and metrics
        """
        # Get changed files
        changed_files = self.get_changed_files()
        if not changed_files:
            return {
                "success": False,
                "message": "No changed files found",
                "commits_created": 0,
                "metrics": self.get_metrics(),
            }

        # Classify files into stages
        classified = self.classify_files(changed_files)

        commits_created = 0
        stages_executed = []

        # Execute stages in order
        for stage in self.stages:
            files = classified.get(stage.name, [])
            if files:
                success = self.create_stage_commit(
                    stage_name=stage.name,
                    files=files,
                    message=message_template,
                    dry_run=dry_run,
                )
                if success:
                    commits_created += 1
                    stages_executed.append(stage.name)

        return {
            "success": commits_created > 0,
            "message": f"Created {commits_created} commits across {len(stages_executed)} stages",
            "commits_created": commits_created,
            "stages_executed": stages_executed,
            "classified_files": classified,
            "metrics": self.get_metrics(),
        }

    def get_metrics(self) -> Dict[str, any]:
        """Get current metrics as dictionary."""
        return {
            "commits_per_pr": self.metrics.commits_per_pr,
            "pr_review_time_minutes": self.metrics.pr_review_time_minutes,
            "stages_completed": self.metrics.stages_completed,
            "total_files_staged": self.metrics.total_files_staged,
        }


def get_commit_strategy(working_directory: Optional[str] = None) -> CommitStrategy:
    """
    Convenience factory function for creating CommitStrategy instance.

    Args:
        working_directory: Git repository directory

    Returns:
        CommitStrategy instance
    """
    return CommitStrategy(working_directory=working_directory)
