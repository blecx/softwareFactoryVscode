#!/usr/bin/env python3
"""Helpers for generating and publishing split issue stubs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List
import re


_NON_ACTIONABLE_STEP_PREFIXES = (
    "current plan estimate:",
    "estimated manual effort:",
    "guardrail max:",
    "parent estimated manual effort:",
    "keep implementation and validation within",
    "work not directly required for this split slice",
)


@dataclass(frozen=True)
class SplitIssueDraft:
    """Draft payload for a split child issue."""

    title: str
    body: str


def extract_split_steps(recommendation_text: str, max_items: int = 3) -> List[str]:
    """Extract actionable split steps from recommendation text."""
    if not recommendation_text:
        return []

    steps: list[str] = []
    for raw_line in recommendation_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", line)
        numbered_match = re.match(r"^\d+[.)]\s+(.*)$", line)

        candidate = ""
        if bullet_match:
            candidate = bullet_match.group(1).strip()
        elif numbered_match:
            candidate = numbered_match.group(1).strip()

        if candidate and not candidate.lower().startswith(
            _NON_ACTIONABLE_STEP_PREFIXES
        ):
            steps.append(candidate)

    if max_items > 0:
        return steps[:max_items]
    return steps


def extract_in_scope_steps(issue_body: str, max_items: int = 3) -> List[str]:
    """Extract actionable bullets from the parent issue In Scope section."""
    if not issue_body:
        return []

    lines = issue_body.splitlines()
    in_scope = False
    steps: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        lowered = line.lower()

        if lowered.startswith("### "):
            heading = lowered[4:].strip()
            in_scope = heading == "in scope"
            continue

        if in_scope and lowered.startswith("## "):
            break

        if not in_scope:
            continue

        bullet_match = re.match(r"^[-*]\s+(.*)$", line)
        if not bullet_match:
            continue

        candidate = bullet_match.group(1).strip()
        if not candidate or candidate.lower().startswith(_NON_ACTIONABLE_STEP_PREFIXES):
            continue
        steps.append(candidate)

    if max_items > 0:
        return steps[:max_items]
    return steps


def generate_split_issue_stubs(
    *,
    parent_issue_number: int,
    estimated_minutes: int | None,
    recommendation_text: str,
    parent_issue_body: str = "",
    max_issues: int = 3,
) -> List[SplitIssueDraft]:
    """Generate issue stubs from split recommendation text."""
    steps = extract_split_steps(recommendation_text, max_items=max_issues)
    if not steps:
        steps = extract_in_scope_steps(parent_issue_body, max_items=max_issues)
    if not steps:
        steps = [
            "Create foundational planning/spec split with explicit acceptance criteria",
            "Implement first execution slice with focused tests",
            "Finalize remaining slice and documentation updates",
        ][: max_issues if max_issues > 0 else 3]

    estimate_label = "unknown" if estimated_minutes is None else str(estimated_minutes)

    drafts: list[SplitIssueDraft] = []
    for index, step in enumerate(steps, start=1):
        title = f"split(#{parent_issue_number}): slice {index} - {step[:70]}"
        body = (
            "## Goal / Problem Statement\n"
            f"Follow-up split issue from #{parent_issue_number} to keep manual execution below 20 minutes.\n\n"
            "## Scope\n"
            "### In Scope\n"
            f"- {step}\n"
            "- Keep implementation and validation within a small, reviewable slice.\n\n"
            "### Out of Scope\n"
            "- Work not directly required for this split slice.\n\n"
            "## Acceptance Criteria\n"
            "- [ ] Scoped implementation is complete and validated.\n"
            "- [ ] Changes remain within one reviewable PR.\n"
            "- [ ] No sensitive files committed (`projectDocs/`, `configs/llm.json`).\n\n"
            "## Additional Context\n"
            f"- Parent issue: #{parent_issue_number}\n"
            f"- Parent estimated manual effort: {estimate_label} minutes\n"
        )
        drafts.append(SplitIssueDraft(title=title, body=body))

    return drafts
