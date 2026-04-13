"""RouterAgent — complexity scoring and model tier assignment for FACTORY.

Given a GitHub issue, RouterAgent:
  1. Scores complexity (0-10) using ComplexityScorer heuristics
  2. Looks up mcp-memory for similar past issues and adjusts score
  3. Assigns model tier: "mini" (gpt-4o-mini) for score ≤5, "full" (gpt-4o) for ≥6
  4. Creates a task run on mcp-agent-bus and transitions status to "routing"
  5. Returns a RoutingDecision with all metadata

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #713
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from factory_runtime.agents.mcp_client import MCPMultiClient

from factory_runtime.agents.complexity_scorer import ComplexityScorer

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RoutingDecision:
    """Result of routing one issue.  Stored in agent-bus context packet."""

    run_id: str
    issue_number: int
    repo: str
    complexity_score: int
    coder_model_tier: str  # "mini" | "full"
    score_breakdown: dict[str, Any]  # per-dimension scores from ComplexityScorer
    planning_model_tier: str = "full"  # always premium for planning
    similar_issues: list[dict[str, Any]] = field(default_factory=list)
    memory_adjustment: int = 0  # ±adjustment applied from memory lookup
    estimated_minutes: Optional[int] = None


# ---------------------------------------------------------------------------
# RouterAgent
# ---------------------------------------------------------------------------

# Heuristic: estimate ~10 min per complexity point as a rough baseline
_MINUTES_PER_SCORE = 10

# Extract file paths from issue body (lines like "- `path/to/file.py`")
_FILE_PATH_RE = re.compile(r"`([\w./\-_]+\.(?:py|ts|tsx|js|md|yml|yaml|json))`")


class RouterAgent:
    """Routes a GitHub issue to the right model tier before coding begins.

    Requires MCPMultiClient to be connected to at least:
     - mcp-memory    (for memory_search_similar)
     - mcp-agent-bus (for bus_create_run, bus_set_status)
    """

    def __init__(
        self,
        mcp_client: "MCPMultiClient",
        scorer: Optional[ComplexityScorer] = None,
    ) -> None:
        self._mcp = mcp_client
        self._scorer = scorer or ComplexityScorer()

    async def route(
        self,
        issue_number: int,
        issue_title: str,
        issue_body: str,
        repo: str = "",
        changed_files: Optional[list[str]] = None,
    ) -> RoutingDecision:
        """Analyse an issue and return a RoutingDecision.

        Steps:
          1. Extract hinted file paths from issue body
          2. Look up similar past issues in mcp-memory
          3. Score complexity (with memory adjustment)
          4. Create a task run on agent-bus
          5. Transition run status to "routing"
          6. Return RoutingDecision

        Args:
            issue_number: GitHub issue number.
            issue_title:  Issue title (used for memory search query).
            issue_body:   Full issue body markdown.
            repo:         GitHub repo slug (owner/repo).
            changed_files: Optional explicit file hints from the caller.

        Returns:
            RoutingDecision with run_id and all routing metadata.
        """
        # Step 1: extract file hints from body
        hinted_files = list(dict.fromkeys(_FILE_PATH_RE.findall(issue_body)))
        if changed_files:
            hinted_files.extend(
                path
                for path in changed_files
                if path and path not in hinted_files
            )

        # Step 2: memory lookup for similar past issues
        similar, memory_adj = await self._memory_lookup(issue_title)

        # Step 3: score complexity
        raw_score, breakdown = self._scorer.score(
            issue_body=issue_body,
            changed_files=hinted_files,
            memory_adjustment=memory_adj,
        )
        tier = ComplexityScorer.model_tier(raw_score)

        # Step 4: create task run on agent-bus
        run_result = await self._mcp.call_tool(
            "bus_create_run",
            {"issue_number": issue_number, "repo": repo},
        )
        run_id = run_result["run_id"]

        # Step 5: transition status to "routing"
        await self._mcp.call_tool(
            "bus_set_status", {"run_id": run_id, "status": "routing"}
        )

        return RoutingDecision(
            run_id=run_id,
            issue_number=issue_number,
            repo=repo,
            complexity_score=raw_score,
            coder_model_tier=tier,
            score_breakdown={
                "file_count": breakdown.file_count_score,
                "cross_service": breakdown.cross_service_score,
                "domain_count": breakdown.domain_count_score,
                "breaking": breakdown.breaking_score,
                "test_gap": breakdown.test_gap_score,
            },
            similar_issues=similar,
            memory_adjustment=memory_adj,
            estimated_minutes=max(5, raw_score * _MINUTES_PER_SCORE),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _memory_lookup(self, query: str) -> tuple[list[dict[str, Any]], int]:
        """Search mcp-memory for similar past issues.

        Returns (similar_issues_list, memory_adjustment_int).
        Adjustment logic:
          - If past similar issues had >50% failures → +1 (likely harder)
          - If past similar issues had 100% success → -1 (likely easier)
          - Otherwise → 0
        """
        try:
            result = await self._mcp.call_tool(
                "memory_search_similar",
                {"query": query, "limit": 5},
            )
            similar = result.get("results", []) if isinstance(result, dict) else []
        except Exception:
            # Memory lookup is best-effort — never block routing
            similar = []

        if not similar:
            return similar, 0

        n = len(similar)
        failures = sum(1 for s in similar if s.get("outcome") == "failure")
        failure_rate = failures / n

        if failure_rate > 0.5:
            adj = 1  # harder than expected historically
        elif failure_rate == 0.0 and n >= 2:
            adj = -1  # consistently easy historically
        else:
            adj = 0

        return similar, adj
