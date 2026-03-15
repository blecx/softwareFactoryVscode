"""mcp-memory: Knowledge graph MCP server for FACTORY long-term agent memory.

Provides three memory layers:
- Short-term: recent issue context (last 10 runs)
- Long-term: lessons learned per issue (persists forever)
- Knowledge graph: entity relationships (file ↔ domain ↔ issue)

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #708
"""
