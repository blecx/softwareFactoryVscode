"""ComplexityScorer — heuristic complexity scoring for GitHub issues.

Scores an issue 0-10 based on:
  1. File count         (0-2 pts)
  2. Cross-service edits (0-2 pts)
  3. Domain count       (0-2 pts)
  4. Breaking API changes (0-2 pts)
  5. Test coverage gap  (0-2 pts)

Score 0-5  → model_tier "mini" (gpt-4o-mini)
Score 6-10 → model_tier "full" (gpt-4o)

No LLM required — fully deterministic from issue body text and file paths.

See: docs/agents/MAESTRO-DESIGN.md
Implements: GitHub issue #713
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Heuristic signals
# ---------------------------------------------------------------------------

# Keywords that suggest a breaking API change
_BREAKING_KEYWORDS = re.compile(
    r"\b(break|breaking|rename|remov[ei]|deprecat|incompatible|migration|drop)\b",
    re.IGNORECASE,
)

# Keywords that suggest the issue involves creating/modifying tests
_TEST_GAP_KEYWORDS = re.compile(
    r"\b(no test|missing test|untested|add test|test coverage|coverage gap)\b",
    re.IGNORECASE,
)

# Core service directories — cross-service if > 1 service is touched
_SERVICE_DIRS = [
    "apps/api/",
    "apps/tui/",
    "apps/mcp/",
    "agents/",
    "client/",
    "_external/",
]

# Core domain names — recognized from paths and text
_DOMAIN_PATTERN = re.compile(
    r"\b(template|blueprint|proposal|artifact|raid|workflow|audit|project|command|governance)\b",
    re.IGNORECASE,
)


@dataclass
class ScoringBreakdown:
    """Per-dimension score breakdown for traceability."""

    file_count_score: int  # 0-2
    cross_service_score: int  # 0-2
    domain_count_score: int  # 0-2
    breaking_score: int  # 0-2
    test_gap_score: int  # 0-2

    @property
    def total(self) -> int:
        return (
            self.file_count_score
            + self.cross_service_score
            + self.domain_count_score
            + self.breaking_score
            + self.test_gap_score
        )


class ComplexityScorer:
    """Heuristic complexity scorer for GitHub issues.

    Input: issue body text + list of file paths expected to change.
    Output: integer score 0-10 with per-dimension breakdown.
    """

    def score(
        self,
        issue_body: str,
        changed_files: list[str],
        *,
        memory_adjustment: int = 0,
    ) -> tuple[int, ScoringBreakdown]:
        """Score an issue for complexity.

        Args:
            issue_body:        Full issue body text (markdown).
            changed_files:     List of expected file paths to change.
            memory_adjustment: ±2 adjustment from historical memory lookup
                               (+1 = past similar issues were harder than they looked,
                                -1 = past similar issues were easier).

        Returns:
            Tuple of (clamped_score_0_to_10, ScoringBreakdown).
        """
        breakdown = ScoringBreakdown(
            file_count_score=self._score_file_count(changed_files),
            cross_service_score=self._score_cross_service(changed_files),
            domain_count_score=self._score_domain_count(issue_body, changed_files),
            breaking_score=self._score_breaking(issue_body),
            test_gap_score=self._score_test_gap(issue_body),
        )
        raw = breakdown.total + memory_adjustment
        return max(0, min(10, raw)), breakdown

    # ------------------------------------------------------------------
    # Scoring dimensions
    # ------------------------------------------------------------------

    def _score_file_count(self, files: list[str]) -> int:
        """More files → higher score.  0: ≤2,  1: 3-6,  2: ≥7"""
        n = len(files)
        if n <= 2:
            return 0
        if n <= 6:
            return 1
        return 2

    def _score_cross_service(self, files: list[str]) -> int:
        """Editing multiple top-level services → higher score.  0: 1,  1: 2,  2: ≥3"""
        touched = set()
        for f in files:
            for svc in _SERVICE_DIRS:
                if f.startswith(svc):
                    touched.add(svc)
                    break
        n = len(touched)
        if n <= 1:
            return 0
        if n == 2:
            return 1
        return 2

    def _score_domain_count(self, body: str, files: list[str]) -> int:
        """Multiple business domains involved → higher score.  0: 1,  1: 2,  2: ≥3"""
        combined = body + " " + " ".join(files)
        domains = set(m.group(1).lower() for m in _DOMAIN_PATTERN.finditer(combined))
        n = len(domains)
        if n <= 1:
            return 0
        if n == 2:
            return 1
        return 2

    def _score_breaking(self, body: str) -> int:
        """Breaking/API change keywords in body → 2, 1 match → 1."""
        matches = len(_BREAKING_KEYWORDS.findall(body))
        if matches == 0:
            return 0
        if matches == 1:
            return 1
        return 2

    def _score_test_gap(self, body: str) -> int:
        """Missing/insufficient tests called out → 2, 1 match → 1."""
        matches = len(_TEST_GAP_KEYWORDS.findall(body))
        if matches == 0:
            return 0
        if matches == 1:
            return 1
        return 2

    @staticmethod
    def model_tier(score: int) -> str:
        """Return model tier string for a given score."""
        return "mini" if score <= 5 else "full"
