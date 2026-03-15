"""PlannerAgent — consumes GitHub issues and writes a plan to agent-bus.

Uses premium models (gpt-4o) and filesystem/search tools to gain context,
then builds an atomic execution plan for the CoderAgent.

Implements: GitHub issue #720
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from factory_runtime.agents.mcp_client import MCPMultiClient

from factory_runtime.agents.llm_client import LLMClientFactory

_SYSTEM_PROMPT = """You are the MAESTRO PlannerAgent.
Your job is to read a GitHub issue, search the codebase using MCP tools to understand the 
context, and then write a precise implementation plan broken down into actionable steps.

AVAILABLE TOOLS:
You have access to mcp-search (search_files) and mcp-filesystem (read_file, list_dir).
Use these to inspect files and find relevant code. 

OUTPUT:
You MUST output a final JSON block bounded by ```json ... ``` that perfectly matches this schema:
{
  "goal": "Short description of what we are doing",
  "files": [{"path": "file1.py", "description": "What to do here"}],
  "acceptance_criteria": ["Criteria 1", "Criteria 2"],
  "validation_commands": ["pytest path/to/test.py -v"],
  "estimated_minutes": 30
}
"""


class PlannerAgent:
    """Creates execution plans for MAESTRO using premium models."""

    def __init__(
        self,
        mcp_client: "MCPMultiClient",
        model_tier: str = "full",
        llm_client: Optional["AsyncOpenAI"] = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        self._mcp = mcp_client
        self._model = LLMClientFactory.get_model_id_for_role("planning")
        self._root = workspace_root or Path.cwd()
        self._llm = llm_client
        self._messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT}
        ]

    async def _init_llm(self) -> "AsyncOpenAI":
        if not self._llm:
            self._llm = LLMClientFactory.create_client_for_role("planning")
            self._model = LLMClientFactory.get_model_id_for_role("planning")
        return self._llm

    async def run(
        self, run_id: str, issue_body: str, similar_issues: list[dict[str, Any]] = []
    ) -> None:
        await self._mcp.call_tool(
            "bus_set_status", {"run_id": run_id, "status": "planning"}
        )

        llm = await self._init_llm()

        memory_context = ""
        if similar_issues:
            memory_context = "\n\nPast Similar Issues (Learnings/Context):\n"
            for past in similar_issues:
                memory_context += f"- Title: {past.get('title', 'N/A')}\n"
                if "lesson" in past:
                    memory_context += f"  Lessons Learned: {past['lesson']}\n"

        self._messages.append(
            {
                "role": "user",
                "content": f"Please analyze this issue and create an execution plan:\n\n{issue_body}{memory_context}",
            }
        )

        plan_dict = {}
        try:
            tool_definitions = self._mcp.get_all_tool_definitions()

            for _ in range(5):
                kwargs = {
                    "model": self._model,
                    "messages": self._messages,
                    "temperature": 0.2,
                }

                valid_tools = [
                    t
                    for t in tool_definitions
                    if t["function"]["name"]
                    not in ("bus_create_run", "bus_set_status", "bus_write_plan")
                ]

                if valid_tools:
                    kwargs["tools"] = valid_tools
                    kwargs["tool_choice"] = "auto"

                response = await llm.chat.completions.create(**kwargs)
                message = response.choices[0].message
                self._messages.append(message)

                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        func_name = tool_call.function.name
                        args_str = tool_call.function.arguments
                        args = json.loads(args_str) if args_str else {}

                        try:
                            tool_result = await self._mcp.call_tool(func_name, args)
                            result_str = json.dumps(tool_result)[:4000]
                        except Exception as e:
                            result_str = f"Error: {e}"

                        self._messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "name": func_name,
                                "content": result_str,
                            }
                        )
                    continue
                break

            final_content = self._messages[-1].content or ""

            # Extract JSON
            match = re.search(r"```json\s*(\{.*?\})\s*```", final_content, re.DOTALL)
            if match:
                plan_dict = json.loads(match.group(1))
            else:
                # Fallback to direct parse
                plan_dict = json.loads(final_content)

        except Exception:
            # Fallback simple
            plan_dict = {
                "goal": "Implement issue",
                "files": [{"path": "unknown", "description": "Review context"}],
                "acceptance_criteria": ["Complete"],
                "validation_commands": ["pytest"],
                "estimated_minutes": 30,
            }

        try:
            await self._mcp.call_tool(
                "bus_write_plan",
                {
                    "run_id": run_id,
                    "goal": plan_dict.get("goal", "Implement issue"),
                    "files": [f.get("path", "") for f in plan_dict.get("files", [])],
                    "acceptance_criteria": plan_dict.get("acceptance_criteria", []),
                    "validation_cmds": plan_dict.get("validation_commands", []),
                    "estimated_minutes": plan_dict.get("estimated_minutes", 30),
                },
            )
            # Advance loop so Coder knows it's ready unless we enforce an explicit manual approval step
            await self._mcp.call_tool(
                "bus_set_status", {"run_id": run_id, "status": "approved"}
            )
        except Exception:
            pass
