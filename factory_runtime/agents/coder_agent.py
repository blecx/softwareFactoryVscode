"""CoderAgent — single persistent thread coder for MAESTRO.

Replaces the old 3-agent chain (planning→coding→review) with ONE ChatAgent
thread that holds all context across every phase. Nothing is lost between
phases because all state stays in a single message list + agent-bus.

Lifecycle:
  1. Read full context packet from agent-bus
  2. Generate implementation plan via LLM
  3. Write plan to agent-bus → transition to awaiting_approval
  4. Poll agent-bus until status == "approved" (human approval gate)
  5. Implement changes (file edits via LLM guidance)
  6. Run validation commands (up to MAX_RETRIES times)
  7. Write file snapshots + validation results to agent-bus
  8. Return CoderResult

See: docs/agents/MAESTRO-DESIGN.md
Implements: GitHub issue #714
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from openai import AsyncOpenAI
    from factory_runtime.agents.mcp_client import MCPMultiClient


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_VALIDATION_RETRIES = 3
APPROVAL_POLL_INTERVAL_SEC = 5.0
APPROVAL_TIMEOUT_SEC = 300.0  # 5 minutes before giving up waiting for human

_MODEL_MAP = {
    "mini": "gpt-4o-mini",
    "full": "gpt-4o",
}

_SYSTEM_PROMPT = """\
You are MAESTRO CoderAgent — an expert software engineer implementing GitHub issues.

Your workflow:
1. Read the full context packet (issue, plan, snapshots, validations).
2. Determine exactly which files to create/modify.
3. For each file: produce the COMPLETE new content (not a diff).
4. After all edits: list the validation commands to run.

Response format for file edits:
```json
{
  "phase": "coding",
  "file_edits": [
    {"filepath": "relative/path/to/file.py", "content": "full file content here"},
    ...
  ],
  "validation_commands": ["pytest tests/unit/", "python -m flake8 apps/api/"]
}
```

Response format for planning:
```json
{
  "phase": "planning",
  "goal": "one-sentence description",
  "files": ["list", "of", "file", "paths"],
  "acceptance_criteria": ["criterion 1", "criterion 2"],
  "validation_commands": ["pytest tests/unit/"],
  "estimated_minutes": 30
}
```

Always output valid JSON. Do not add explanations outside the JSON block.
"""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class CoderResult:
    """Result returned after a coder run completes."""

    run_id: str
    files_changed: list[str] = field(default_factory=list)
    tests_passed: bool = False
    pr_ready: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and self.tests_passed


# ---------------------------------------------------------------------------
# CoderAgent
# ---------------------------------------------------------------------------


class CoderAgent:
    """Single persistent thread coder.  One instance = one task run."""

    def __init__(
        self,
        mcp_client: "MCPMultiClient",
        model_tier: str = "mini",
        llm_client: Optional["AsyncOpenAI"] = None,
        workspace_root: Optional[Path] = None,
    ) -> None:
        """
        Args:
            mcp_client:     Connected MCPMultiClient (memory + agent-bus tools).
            model_tier:     "mini" (gpt-4o-mini) or "full" (gpt-4o).
            llm_client:     Optional AsyncOpenAI client (injected for testing).
                            If None, creates one via LLMClientFactory.
            workspace_root: Workspace root for file operations (default: cwd).
        """
        self._mcp = mcp_client
        self._model = _MODEL_MAP.get(model_tier, "gpt-4o-mini")
        self._llm = llm_client  # set lazily if None
        self._root = workspace_root or Path.cwd()
        self._messages: list[dict[str, str]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, run_id: str) -> CoderResult:
        """Execute the full coding lifecycle for one task run.

        Returns CoderResult. Never raises — errors are captured in result.error.
        """
        try:
            return await self._run_lifecycle(run_id)
        except Exception as exc:  # noqa: BLE001
            await self._safe_set_status(run_id, "failed")
            return CoderResult(run_id=run_id, error=str(exc))

    # ------------------------------------------------------------------
    # Lifecycle phases
    # ------------------------------------------------------------------

    async def _run_lifecycle(self, run_id: str) -> CoderResult:
        # ── Phase 1: Read context ─────────────────────────────────────
        packet = await self._mcp.call_tool(
            "bus_read_context_packet", {"run_id": run_id}
        )
        run_info = packet["run"]
        existing_plan = packet.get("plan")

        # ── Phase 2: Generate plan (if not already approved) ──────────
        if existing_plan is None or run_info["status"] not in ("approved", "coding"):
            await self._mcp.call_tool(
                "bus_set_status", {"run_id": run_id, "status": "planning"}
            )
            plan = await self._generate_plan(packet)
            await self._mcp.call_tool(
                "bus_write_plan",
                {
                    "run_id": run_id,
                    "goal": plan.get("goal", ""),
                    "files": plan.get("files", []),
                    "acceptance_criteria": plan.get("acceptance_criteria", []),
                    "validation_cmds": plan.get("validation_commands", []),
                    "estimated_minutes": plan.get("estimated_minutes"),
                },
            )
            await self._mcp.call_tool(
                "bus_set_status", {"run_id": run_id, "status": "awaiting_approval"}
            )
            await self._mcp.call_tool(
                "bus_write_checkpoint",
                {
                    "run_id": run_id,
                    "label": "plan_generated",
                    "metadata": {"files_count": len(plan.get("files", []))},
                },
            )

            # ── Phase 3: Wait for approval ────────────────────────────
            approved = await self._wait_for_approval(run_id)
            if not approved:
                return CoderResult(
                    run_id=run_id,
                    error="Approval timeout — run manually approved or retry",
                )

        # Re-read packet after approval (may have feedback)
        packet = await self._mcp.call_tool(
            "bus_read_context_packet", {"run_id": run_id}
        )

        # ── Phase 4: Implement ────────────────────────────────────────
        await self._mcp.call_tool(
            "bus_set_status", {"run_id": run_id, "status": "coding"}
        )
        files_changed = await self._implement(run_id, packet)
        await self._mcp.call_tool(
            "bus_write_checkpoint",
            {
                "run_id": run_id,
                "label": "coding_complete",
                "metadata": {"files_changed": files_changed},
            },
        )

        # ── Phase 5: Validate ─────────────────────────────────────────
        await self._mcp.call_tool(
            "bus_set_status", {"run_id": run_id, "status": "validating"}
        )
        plan_data = packet.get("plan") or {}
        validation_cmds = (
            plan_data.get("validation_cmds")
            or plan_data.get("validation_commands")
            or []
        )
        passed = await self._validate_with_retry(run_id, validation_cmds)

        if passed:
            await self._mcp.call_tool(
                "bus_write_checkpoint",
                {
                    "run_id": run_id,
                    "label": "validation_passed",
                    "metadata": {},
                },
            )

        # ── Phase 6: Review + done ────────────────────────────────────
        await self._mcp.call_tool(
            "bus_set_status", {"run_id": run_id, "status": "reviewing"}
        )
        if passed:
            await self._mcp.call_tool(
                "bus_set_status", {"run_id": run_id, "status": "pr_created"}
            )

        return CoderResult(
            run_id=run_id,
            files_changed=files_changed,
            tests_passed=passed,
            pr_ready=passed,
        )

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------

    async def _chat(self, user_message: str) -> str:
        """Add user message, call LLM, return assistant reply. Accumulates history."""
        if self._llm is None:
            from factory_runtime.agents.llm_client import LLMClientFactory

            self._llm = LLMClientFactory.create_client_for_role("coding")

        if not self._messages:
            self._messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

        self._messages.append({"role": "user", "content": user_message})
        response = await self._llm.chat.completions.create(
            model=self._model,
            messages=self._messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        reply = response.choices[0].message.content or "{}"
        self._messages.append({"role": "assistant", "content": reply})
        return reply

    async def _generate_plan(self, packet: dict[str, Any]) -> dict[str, Any]:
        """Ask LLM to produce an implementation plan from the context packet."""
        prompt = (
            f"Issue #{packet['run']['issue_number']} in {packet['run']['repo']}.\n\n"
            f"Context packet:\n```json\n{json.dumps(packet, indent=2)}\n```\n\n"
            "Produce a planning phase response."
        )
        raw = await self._chat(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {
                "goal": "Plan generation failed",
                "files": [],
                "acceptance_criteria": [],
                "validation_commands": [],
            }

    async def _implement(self, run_id: str, packet: dict[str, Any]) -> list[str]:
        """Ask LLM to produce file edits and apply them. Returns list of changed paths."""
        feedback = (packet.get("plan") or {}).get("feedback", "")
        prompt = (
            f"Approved context packet:\n```json\n{json.dumps(packet, indent=2)}\n```\n"
            + (f"\nReviewer feedback: {feedback}\n" if feedback else "")
            + "\nProduce a coding phase response with all file edits."
        )
        raw = await self._chat(prompt)
        try:
            response = json.loads(raw)
        except json.JSONDecodeError:
            return []

        files_changed: list[str] = []
        for edit in response.get("file_edits", []):
            filepath = edit.get("filepath", "")
            content = edit.get("content", "")
            if not filepath:
                continue

            target = self._root / filepath
            before = target.read_text() if target.exists() else None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            files_changed.append(filepath)

            # Write snapshot to agent-bus
            await self._mcp.call_tool(
                "bus_write_snapshot",
                {
                    "run_id": run_id,
                    "filepath": filepath,
                    "content_before": before,
                    "content_after": content,
                },
            )

        return files_changed

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def _validate_with_retry(self, run_id: str, commands: list[str]) -> bool:
        """Run validation commands, retrying in same thread up to MAX_VALIDATION_RETRIES."""
        if not commands:
            return True

        for attempt in range(1, MAX_VALIDATION_RETRIES + 1):
            all_passed = True
            for cmd in commands:
                passed, stdout, stderr, rc = await self._run_command(cmd)
                await self._mcp.call_tool(
                    "bus_write_validation",
                    {
                        "run_id": run_id,
                        "command": cmd,
                        "stdout": stdout,
                        "stderr": stderr,
                        "exit_code": rc,
                        "passed": passed,
                    },
                )
                if not passed:
                    all_passed = False

            if all_passed:
                return True

            if attempt < MAX_VALIDATION_RETRIES:
                # Ask LLM to fix the failures (in same thread — no context lost)
                last_results = await self._mcp.call_tool(
                    "bus_read_context_packet", {"run_id": run_id}
                )
                failures = [
                    v
                    for v in last_results.get("validation_results", [])
                    if not v.get("passed")
                ]
                fix_prompt = (
                    f"Validation attempt {attempt} failed. Failing results:\n"
                    f"```json\n{json.dumps(failures, indent=2)}\n```\n"
                    "Produce a coding phase response that fixes these failures."
                )
                raw = await self._chat(fix_prompt)
                try:
                    fix_response = json.loads(raw)
                    for edit in fix_response.get("file_edits", []):
                        filepath = edit.get("filepath", "")
                        content = edit.get("content", "")
                        if filepath and content:
                            target = self._root / filepath
                            before = target.read_text() if target.exists() else None
                            target.parent.mkdir(parents=True, exist_ok=True)
                            target.write_text(content)
                            await self._mcp.call_tool(
                                "bus_write_snapshot",
                                {
                                    "run_id": run_id,
                                    "filepath": filepath,
                                    "content_before": before,
                                    "content_after": content,
                                },
                            )
                except json.JSONDecodeError:
                    pass

        return False

    async def _run_command(self, cmd: str) -> tuple[bool, str, str, int]:
        """Run a shell command and return (passed, stdout, stderr, exit_code)."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self._root),
            )
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=120)
            rc = proc.returncode or 0
            return (
                rc == 0,
                stdout_b.decode(errors="replace"),
                stderr_b.decode(errors="replace"),
                rc,
            )
        except asyncio.TimeoutError:
            return False, "", "Command timed out after 120s", 1
        except Exception as exc:  # noqa: BLE001
            return False, "", str(exc), 1

    # ------------------------------------------------------------------
    # Approval polling
    # ------------------------------------------------------------------

    async def _wait_for_approval(self, run_id: str) -> bool:
        """Poll agent-bus until run status transitions to 'approved'."""
        elapsed = 0.0
        while elapsed < APPROVAL_TIMEOUT_SEC:
            await asyncio.sleep(APPROVAL_POLL_INTERVAL_SEC)
            elapsed += APPROVAL_POLL_INTERVAL_SEC
            try:
                packet = await self._mcp.call_tool(
                    "bus_read_context_packet", {"run_id": run_id}
                )
                if packet["run"]["status"] == "approved":
                    return True
                if packet["run"]["status"] == "failed":
                    return False
            except Exception:  # noqa: BLE001
                pass
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _safe_set_status(self, run_id: str, status: str) -> None:
        """Best-effort status update — never raises."""
        try:
            await self._mcp.call_tool(
                "bus_set_status", {"run_id": run_id, "status": status}
            )
        except Exception:  # noqa: BLE001
            pass
