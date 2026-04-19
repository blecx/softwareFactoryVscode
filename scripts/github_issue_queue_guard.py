#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

STATE_PATH = Path(".tmp/github-issue-queue-state.md")
WORKFLOW_DOC = "docs/WORK-ISSUE-WORKFLOW.md"
GUARDRAILS_DOC = ".github/copilot-instructions.md"

START_PATTERNS = [
    r"/execute github issues in order",
    r"\bexecute github issues\b",
    r"\bstart (the )?(issue )?queue\b",
    r"\bbegin (the )?(issue )?queue\b",
    r"\bstart with issue\b",
    r"\bresolve issue #?\d+\b",
]

CONTINUATION_PATTERNS = [
    r"\bcontinue (with|to)? ?(the )?(next )?issue\b",
    r"\bcontinue the queue\b",
    r"\bresume (the )?(issue )?queue\b",
    r"\bkeep going\b",
    r"\bmove on to the next issue\b",
    r"\bqueue-backend\b",
    r"\bqueue-phase-2\b",
    r"\bnext issue\b",
]

MERGE_PATTERNS = [
    r"\bmerge (the )?pr\b",
    r"\bmerge issue\b",
    r"\bpr-merge\b",
]

COMPLETION_PATTERNS = [
    r"\bclose (the )?issue\b",
    r"\bmark (the )?issue as done\b",
    r"\bmark (the )?issue complete\b",
    r"\bcomplete (the )?issue\b",
    r"\bresolve (the )?issue\b",
]

REQUIRED_KEYS = {
    "active_issue",
    "active_branch",
    "active_pr",
    "status",
    "last_validation",
    "next_gate",
    "blocker",
}

GITHUB_EVIDENCE_KEYS = {
    "issue_state",
    "pr_state",
    "ci_state",
    "cleanup_state",
    "last_github_truth",
}

NEXT_ALLOWED_STATUSES = {"merged-and-closed", "waiting-for-approval", "blocked"}
MERGE_ALLOWED_STATUSES = {"ready-for-pr-merge"}
COMPLETION_ALLOWED_STATUSES = {"merged-and-closed"}

EMPTY_TOKENS = {
    "",
    "none",
    "null",
    "n-a",
    "na",
    "unknown",
    "unverified",
    "not-verified",
    "not-checked",
    "not-recorded",
}

OPEN_ISSUE_STATES = {
    "open",
    "open-verified",
    "open-verified-on-github",
    "open-on-github",
}

MERGEABLE_PR_STATES = {
    "open",
    "open-verified",
    "open-and-mergeable",
    "open-and-mergeable-on-github",
    "ready-to-merge",
}

MERGED_PR_STATES = {
    "merged",
    "merged-verified",
    "merged-verified-on-github",
    "merged-on-github",
}

CLOSED_ISSUE_STATES = {
    "closed",
    "closed-verified",
    "closed-verified-on-github",
    "closed-on-github",
}

PASSING_CI_STATES = {
    "green",
    "passed",
    "passed-on-github",
    "success",
    "verified-passed",
}

PRE_MERGE_CLEANUP_STATES = {
    "clean",
    "clean-verified",
    "not-applicable",
    "pending-post-merge",
}

POST_MERGE_CLEANUP_STATES = {
    "clean",
    "clean-verified",
    "complete",
    "completed",
    "not-applicable",
}


def build_continue(system_message: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"continue": True}
    if system_message:
        payload["systemMessage"] = system_message
    return payload


def build_stop(stop_reason: str, system_message: str) -> dict[str, Any]:
    return {
        "continue": False,
        "stopReason": stop_reason,
        "systemMessage": system_message,
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0


def workflow_hint() -> str:
    return (
        f"See `{WORKFLOW_DOC}` and `{GUARDRAILS_DOC}` for the canonical "
        "issue → PR → merge guardrails."
    )


def load_payload() -> dict[str, Any]:
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"rawPayload": data}
    except json.JSONDecodeError:
        return {"rawStdin": raw}


def iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str):
                yield key
            yield from iter_strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_strings(item)


def extract_prompt_text(payload: dict[str, Any]) -> str:
    candidates: list[str] = []
    priority_keys = {"prompt", "userPrompt", "message", "text", "input"}

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in priority_keys and isinstance(item, str):
                    candidates.append(item)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(payload)
    if candidates:
        return max(candidates, key=len)

    flattened = [s for s in iter_strings(payload) if len(s.strip()) > 8]
    return max(flattened, key=len) if flattened else ""


def matches_any(prompt: str, patterns: list[str]) -> bool:
    lowered = prompt.lower()
    return any(re.search(pattern, lowered) for pattern in patterns)


def normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")


def value_is_empty(value: str) -> bool:
    return normalize_token(value) in EMPTY_TOKENS


def value_matches(state: dict[str, str], key: str, allowed: set[str]) -> bool:
    return normalize_token(state.get(key, "")) in allowed


def missing_truth_keys(state: dict[str, str]) -> list[str]:
    return sorted(
        key for key in GITHUB_EVIDENCE_KEYS if value_is_empty(state.get(key, ""))
    )


def parse_state_file(
    state_path: Path = STATE_PATH,
) -> tuple[dict[str, str] | None, str | None]:
    if not state_path.exists():
        return None, "missing"

    state: dict[str, str] = {}
    for raw_line in state_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line.startswith("- ") or ":" not in line:
            continue
        key, value = line[2:].split(":", 1)
        state[key.strip()] = value.strip()

    missing_keys = sorted(REQUIRED_KEYS - state.keys())
    if missing_keys:
        return state, f"incomplete:{', '.join(missing_keys)}"

    return state, None


def validate_merge_gate(state: dict[str, str]) -> str | None:
    if value_is_empty(state.get("active_pr", "")):
        return (
            "Blocked by repo workflow guardrails: the checkpoint does not record an "
            "active PR. Re-check GitHub truth, update `.tmp/github-issue-queue-state.md`, "
            f"and only then continue toward merge. {workflow_hint()}"
        )

    if normalize_token(state["status"]) not in MERGE_ALLOWED_STATUSES:
        return (
            "Blocked by repo workflow guardrails: the checkpoint status must be "
            "`ready-for-pr-merge` before merge narration is permitted. Update the "
            f"checkpoint after validation and GitHub checks. {workflow_hint()}"
        )

    if value_is_empty(state.get("last_validation", "")):
        return (
            "Blocked by repo workflow guardrails: local validation evidence is missing. "
            "Run `./.venv/bin/python ./scripts/local_ci_parity.py`, record the result in "
            "`.tmp/github-issue-queue-state.md`, and try again. "
            f"{workflow_hint()}"
        )

    missing_keys = missing_truth_keys(state)
    if missing_keys:
        return (
            "Blocked by repo workflow guardrails: merge-safe GitHub truth evidence is "
            f"missing for {', '.join(missing_keys)}. Update `.tmp/github-issue-queue-state.md` "
            "with current GitHub issue, PR, CI, cleanup, and truth-check evidence before "
            f"continuing. {workflow_hint()}"
        )

    if not value_matches(state, "issue_state", OPEN_ISSUE_STATES):
        return (
            "Blocked by repo workflow guardrails: `issue_state` must show the linked issue "
            "is still open and verified on GitHub before merge handoff. "
            f"{workflow_hint()}"
        )

    if not value_matches(state, "pr_state", MERGEABLE_PR_STATES):
        return (
            "Blocked by repo workflow guardrails: `pr_state` must show an open, mergeable PR "
            "verified on GitHub before merge narration is permitted. "
            f"{workflow_hint()}"
        )

    if not value_matches(state, "ci_state", PASSING_CI_STATES):
        return (
            "Blocked by repo workflow guardrails: `ci_state` must confirm passing required "
            "checks on GitHub before merge narration is permitted. "
            f"{workflow_hint()}"
        )

    if not value_matches(state, "cleanup_state", PRE_MERGE_CLEANUP_STATES):
        return (
            "Blocked by repo workflow guardrails: `cleanup_state` must confirm the local "
            "cleanup gate is known (`pending-post-merge`, `not-applicable`, or already clean) "
            "before merge narration is permitted. "
            f"{workflow_hint()}"
        )

    return None


def validate_completion_gate(state: dict[str, str]) -> str | None:
    if value_is_empty(state.get("active_pr", "")):
        return (
            "Blocked by repo workflow guardrails: the checkpoint does not record an active PR. "
            "Verify GitHub truth and update `.tmp/github-issue-queue-state.md` before using "
            f"completion or close narration. {workflow_hint()}"
        )

    if normalize_token(state["status"]) not in COMPLETION_ALLOWED_STATUSES:
        return (
            "Blocked by repo workflow guardrails: completion narration is only allowed when "
            "the checkpoint status is `merged-and-closed`. Re-check GitHub truth, cleanup, "
            f"and checkpoint state first. {workflow_hint()}"
        )

    if value_is_empty(state.get("last_validation", "")):
        return (
            "Blocked by repo workflow guardrails: completion narration still requires recorded "
            "local validation evidence. Update `.tmp/github-issue-queue-state.md` with the last "
            f"successful precheck command. {workflow_hint()}"
        )

    missing_keys = missing_truth_keys(state)
    if missing_keys:
        return (
            "Blocked by repo workflow guardrails: completion evidence is missing for "
            f"{', '.join(missing_keys)}. Update `.tmp/github-issue-queue-state.md` with GitHub "
            f"issue, PR, CI, cleanup, and truth-check evidence first. {workflow_hint()}"
        )

    if not value_matches(state, "issue_state", CLOSED_ISSUE_STATES):
        return (
            "Blocked by repo workflow guardrails: `issue_state` must confirm the linked issue "
            "is closed on GitHub before completion narration is permitted. "
            f"{workflow_hint()}"
        )

    if not value_matches(state, "pr_state", MERGED_PR_STATES):
        return (
            "Blocked by repo workflow guardrails: `pr_state` must confirm the PR is merged on "
            f"GitHub before completion narration is permitted. {workflow_hint()}"
        )

    if not value_matches(state, "ci_state", PASSING_CI_STATES):
        return (
            "Blocked by repo workflow guardrails: `ci_state` must confirm passing required "
            f"checks before completion narration is permitted. {workflow_hint()}"
        )

    if not value_matches(state, "cleanup_state", POST_MERGE_CLEANUP_STATES):
        return (
            "Blocked by repo workflow guardrails: `cleanup_state` must confirm post-merge local "
            f"cleanup is complete before completion narration is permitted. {workflow_hint()}"
        )

    return None


def evaluate_prompt(prompt: str, state_path: Path = STATE_PATH) -> dict[str, Any]:
    prompt = prompt.strip()
    if not prompt:
        return build_continue()

    is_start = matches_any(prompt, START_PATTERNS)
    is_continue = matches_any(prompt, CONTINUATION_PATTERNS)
    is_merge = matches_any(prompt, MERGE_PATTERNS)
    is_completion = matches_any(prompt, COMPLETION_PATTERNS)

    if not (is_start or is_continue or is_merge or is_completion):
        return build_continue()

    state, state_problem = parse_state_file(state_path)

    if is_start and state_problem == "missing":
        return build_continue(
            "Starting ordered issue execution: create `.tmp/github-issue-queue-state.md` "
            "as soon as the active issue is selected."
        )

    if state_problem == "missing":
        return build_stop(
            "Missing ordered-issue checkpoint",
            "Blocked by repo workflow guardrails: `.tmp/github-issue-queue-state.md` is "
            "missing. Re-anchor from GitHub truth or restart with `/Execute GitHub Issues In "
            f"Order`, then create/update the checkpoint before continuing, merging, or closing "
            f"anything. {workflow_hint()}",
        )

    if state_problem and state is not None:
        return build_stop(
            "Incomplete ordered-issue checkpoint",
            "Blocked by repo workflow guardrails: `.tmp/github-issue-queue-state.md` exists "
            "but is incomplete. Required keys: active_issue, active_branch, active_pr, status, "
            f"last_validation, next_gate, blocker. {workflow_hint()}",
        )

    assert state is not None

    if is_continue and normalize_token(state["status"]) not in NEXT_ALLOWED_STATUSES:
        return build_stop(
            "Unsafe next-issue continuation",
            "Blocked by repo workflow guardrails: it is not safe to continue to the next issue "
            f"while the checkpoint status is `{state['status']}`. Finish or safely gate the "
            f"current issue first, then update `.tmp/github-issue-queue-state.md`. "
            f"{workflow_hint()}",
        )

    if is_merge:
        error = validate_merge_gate(state)
        if error:
            return build_stop("Unsafe merge state", error)

    if is_completion:
        error = validate_completion_gate(state)
        if error:
            return build_stop("Unsafe completion state", error)

    return build_continue()


def main() -> int:
    payload = load_payload()
    prompt = extract_prompt_text(payload)
    return emit(evaluate_prompt(prompt))


if __name__ == "__main__":
    raise SystemExit(main())
