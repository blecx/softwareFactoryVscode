"""Pydantic models for the Approval Gate API."""

from typing import Any, Optional
from pydantic import BaseModel


class PlanCard(BaseModel):
    """Structured plan card shown to the human reviewer."""

    run_id: str
    issue_number: int
    repo: str
    status: str
    goal: str
    files: list[str]
    acceptance_criteria: list[str]
    validation_cmds: list[str]
    estimated_minutes: Optional[int] = None
    checkpoints: list[str] = []


class ApprovalRequest(BaseModel):
    """Request body for POST /approve/{run_id}."""

    approved: bool
    feedback: str = ""


class PendingRun(BaseModel):
    """Minimal run summary shown in GET /pending list."""

    run_id: str
    issue_number: int
    repo: str
    created_ts: str
