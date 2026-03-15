"""mcp-agent-bus: Shared context bus MCP server for FACTORY.

Provides structured lossless state storage for one agent task run:
- task_runs    : top-level run record with status + issue metadata
- plans        : approved implementation plan for a run
- file_snapshots: before/after content for every file touched
- validation_results: test/lint command outputs + pass/fail
- checkpoints  : named agent milestones within a run

See: docs/agents/FACTORY-DESIGN.md
Implements: GitHub issue #710
"""
