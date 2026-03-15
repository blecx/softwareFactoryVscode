"""agents.coverage_analyzer

Analyzes test coverage changes and enforces coverage quality gates.

This module helps agents maintain/improve test coverage by:
- Comparing before/after coverage
- Detecting coverage regressions
- Warning about low coverage files
- Tracking coverage metrics
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class CoverageFile:
    """Coverage data for a single file."""

    path: str
    percent_covered: float
    covered_lines: int
    missing_lines: int
    total_lines: int


@dataclass
class CoverageReport:
    """Coverage report with per-file data."""

    total_percent: float
    files: Dict[str, CoverageFile]

    @property
    def total_covered(self) -> int:
        """Total covered lines across all files."""
        return sum(f.covered_lines for f in self.files.values())

    @property
    def total_uncovered(self) -> int:
        """Total uncovered lines across all files."""
        return sum(f.missing_lines for f in self.files.values())


@dataclass
class CoverageDiff:
    """Difference between two coverage reports."""

    total_delta: float  # Percentage point change
    new_lines_covered: int
    new_lines_uncovered: int
    affected_files: List[str]
    low_coverage_files: List[CoverageFile]  # Files below threshold
    regressions: List[str]  # Files with decreased coverage


class CoverageAnalyzer:
    """
    Analyzes test coverage changes and enforces quality gates.

    This analyzer helps maintain high test coverage by:
    - Comparing coverage before/after changes
    - Detecting coverage regressions
    - Warning about files below coverage threshold
    - Providing actionable feedback
    """

    def __init__(
        self,
        coverage_threshold: float = 80.0,
        working_directory: str = ".",
    ):
        """
        Initialize CoverageAnalyzer.

        Args:
            coverage_threshold: Minimum acceptable coverage percentage (default 80%)
            working_directory: Directory to run coverage analysis in
        """
        self.coverage_threshold = coverage_threshold
        self.working_directory = Path(working_directory)
        self.metrics = {
            "coverage_regressions_prevented": 0,
            "average_coverage_delta": 0.0,
            "files_analyzed": 0,
            "warnings_issued": 0,
        }

    def _run_coverage(self) -> Optional[Path]:
        """
        Run pytest with coverage to generate coverage.json.

        Returns:
            Path to coverage.json if successful, None otherwise
        """
        try:
            subprocess.run(
                [
                    "pytest",
                    "tests/",
                    "--cov=apps/api",
                    "--cov=apps/tui",
                    "--cov-report=json",
                    "-q",
                ],
                cwd=self.working_directory,
                capture_output=True,
                text=True,
            )

            coverage_file = self.working_directory / "coverage.json"
            if coverage_file.exists():
                return coverage_file

            return None

        except Exception as e:
            print(f"❌ Error running coverage: {e}")
            return None

    def _parse_coverage_file(self, coverage_file: Path) -> Optional[CoverageReport]:
        """
        Parse coverage.json into CoverageReport.

        Args:
            coverage_file: Path to coverage.json

        Returns:
            CoverageReport if successful, None otherwise
        """
        try:
            with open(coverage_file) as f:
                data = json.load(f)

            total_percent = data.get("totals", {}).get("percent_covered", 0.0)

            files = {}
            for file_path, file_data in data.get("files", {}).items():
                summary = file_data.get("summary", {})
                files[file_path] = CoverageFile(
                    path=file_path,
                    percent_covered=summary.get("percent_covered", 0.0),
                    covered_lines=summary.get("covered_lines", 0),
                    missing_lines=summary.get("missing_lines", 0),
                    total_lines=summary.get("num_statements", 0),
                )

            return CoverageReport(total_percent=total_percent, files=files)

        except Exception as e:
            print(f"❌ Error parsing coverage file: {e}")
            return None

    def get_current_coverage(self) -> Optional[CoverageReport]:
        """
        Get current coverage by running tests.

        Returns:
            CoverageReport if successful, None otherwise
        """
        coverage_file = self._run_coverage()
        if not coverage_file:
            return None

        return self._parse_coverage_file(coverage_file)

    def analyze_coverage_impact(
        self, before: CoverageReport, after: CoverageReport, changed_files: List[str]
    ) -> CoverageDiff:
        """
        Analyze the impact of code changes on test coverage.

        Args:
            before: Coverage report before changes
            after: Coverage report after changes
            changed_files: List of file paths that were modified

        Returns:
            CoverageDiff with analysis results
        """
        # Calculate deltas
        total_delta = after.total_percent - before.total_percent
        new_lines_covered = after.total_covered - before.total_covered
        new_lines_uncovered = after.total_uncovered - before.total_uncovered

        # Identify affected files (changed or new)
        affected_files = []
        for file_path in changed_files:
            if file_path in after.files:
                affected_files.append(file_path)

        # Find low coverage files
        low_coverage_files = []
        for file_path in affected_files:
            file_cov = after.files.get(file_path)
            if file_cov and file_cov.percent_covered < self.coverage_threshold:
                low_coverage_files.append(file_cov)

        # Find regressions (coverage decreased)
        regressions = []
        for file_path in affected_files:
            if file_path in before.files and file_path in after.files:
                before_cov = before.files[file_path].percent_covered
                after_cov = after.files[file_path].percent_covered
                if after_cov < before_cov - 0.1:  # Allow 0.1% tolerance
                    regressions.append(file_path)

        # Update metrics
        self.metrics["files_analyzed"] = len(affected_files)
        self.metrics["average_coverage_delta"] = total_delta
        if regressions:
            self.metrics["coverage_regressions_prevented"] += 1
        if low_coverage_files:
            self.metrics["warnings_issued"] += len(low_coverage_files)

        return CoverageDiff(
            total_delta=total_delta,
            new_lines_covered=new_lines_covered,
            new_lines_uncovered=new_lines_uncovered,
            affected_files=affected_files,
            low_coverage_files=low_coverage_files,
            regressions=regressions,
        )

    def enforce_coverage_rules(self, diff: CoverageDiff) -> bool:
        """
        Enforce coverage rules and provide feedback.

        Args:
            diff: Coverage difference to validate

        Returns:
            True if all rules pass, False if any violations found
        """
        violations = []

        # Rule 1: No coverage regressions
        if diff.regressions:
            violations.append(
                f"❌ Coverage decreased in {len(diff.regressions)} file(s):"
            )
            for file_path in diff.regressions:
                violations.append(f"   - {file_path}")

        # Rule 2: New/changed files must meet threshold
        if diff.low_coverage_files:
            violations.append(
                f"⚠️  {len(diff.low_coverage_files)} file(s) below {self.coverage_threshold}% coverage:"
            )
            for file_cov in diff.low_coverage_files:
                violations.append(
                    f"   - {file_cov.path}: {file_cov.percent_covered:.1f}% (missing {file_cov.missing_lines} lines)"
                )

        # Print results
        if violations:
            print("\n".join(violations))
            return False

        # Success message
        if diff.total_delta >= 0:
            print(
                f"✅ Coverage maintained/improved: {diff.total_delta:+.2f} percentage points"
            )
        else:
            print(
                f"✅ Coverage rules passed (delta: {diff.total_delta:+.2f} percentage points)"
            )

        if diff.affected_files:
            print(f"✅ {len(diff.affected_files)} file(s) analyzed, all passing")

        return True

    def get_metrics(self) -> Dict[str, any]:
        """
        Get coverage analysis metrics.

        Returns:
            Dictionary with metric names and values
        """
        return self.metrics.copy()


def get_coverage_analyzer(
    coverage_threshold: float = 80.0, working_directory: str = "."
) -> CoverageAnalyzer:
    """
    Get a CoverageAnalyzer instance.

    Args:
        coverage_threshold: Minimum acceptable coverage percentage
        working_directory: Directory to run coverage analysis in

    Returns:
        CoverageAnalyzer instance
    """
    return CoverageAnalyzer(
        coverage_threshold=coverage_threshold, working_directory=working_directory
    )
