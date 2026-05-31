import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from factory_runtime.agents.model_selection_policy import ModelSelectionPolicy
from factory_runtime.agents.router_agent import RouterAgent, RoutingDecision


def test_routing_audit_fields():
    # Mock MCP client
    mcp_mock = AsyncMock()
    mcp_mock.call_tool.side_effect = lambda name, args: (
        {"run_id": "test-run"} if name == "bus_create_run" else {}
    )

    # We use default config since tests run in workspace root
    router = RouterAgent(mcp_client=mcp_mock)

    decision = asyncio.run(
        router.route(
            issue_number=1,
            issue_title="Mock issue",
            issue_body="We need to update `file1.py` and `file2.py` in one domain.",
            repo="owner/repo",
        )
    )

    assert hasattr(decision, "is_fit"), "is_fit is required"
    assert hasattr(decision, "action_required"), "action_required is required"
    assert hasattr(
        decision, "fallback_recommendation"
    ), "fallback_recommendation is required"
    assert hasattr(decision, "compact_tool_subset"), "compact_tool_subset is required"

    # Normally "mini" tier works for 2 files, so fit is true unless 10 min heuristic fails it.
    # We just ensure the fields exist and hold lists.
    assert isinstance(decision.fallback_recommendation, list)
    assert isinstance(decision.compact_tool_subset, list)
