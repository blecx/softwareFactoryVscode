import json
import os
import time
from typing import Any, Dict, Optional


def get_evidence_path(evidence_key: str, repo_root: str = ".") -> str:
    """Returns the path to the evidence file under .tmp/ directory."""
    tmp_dir = os.path.join(repo_root, ".tmp")
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)

    # Sanitize key to prevent path traversal
    safe_key = "".join(
        c for c in evidence_key if c.isalnum() or c in ("-", "_")
    ).strip()
    if not safe_key:
        safe_key = "default"

    return os.path.join(tmp_dir, f"workflow_preflight_{safe_key}.json")


def record_preflight_evidence(
    evidence_key: str,
    agent: str,
    status: str,
    repo_root: str = ".",
    # exact-state optional fields
    issue_number: Optional[str] = None,
    pr_number: Optional[str] = None,
    branch: Optional[str] = None,
    worktree: Optional[str] = None,
    request_hash: Optional[str] = None,
    checkpoint_hash: Optional[str] = None,
    github_truth_timestamp: Optional[str] = None,
    expiration_metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Records workflow preflight evidence into a JSON file under .tmp/
    """
    path = get_evidence_path(evidence_key, repo_root)

    evidence = {
        "evidence_key": evidence_key,
        "agent": agent,
        "status": status,
        "timestamp": time.time(),
    }

    if issue_number is not None:
        evidence["issue_number"] = issue_number
    if pr_number is not None:
        evidence["pr_number"] = pr_number
    if branch is not None:
        evidence["branch"] = branch
    if worktree is not None:
        evidence["worktree"] = worktree
    if request_hash is not None:
        evidence["request_hash"] = request_hash
    if checkpoint_hash is not None:
        evidence["checkpoint_hash"] = checkpoint_hash
    if github_truth_timestamp is not None:
        evidence["github_truth_timestamp"] = github_truth_timestamp
    if expiration_metadata is not None:
        evidence["expiration_metadata"] = expiration_metadata

    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)


def require_safe_preflight(
    evidence_key: str,
    required_agent: str,
    ttl_seconds: int = 300,
    repo_root: str = ".",
    exact_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Validates fresh workflow preflight evidence.
    Returns a dict with 'safe_to_continue' and 'blockers'.
    """
    path = get_evidence_path(evidence_key, repo_root)

    if not os.path.exists(path):
        return {
            "safe_to_continue": False,
            "blockers": [f"Missing preflight evidence for key '{evidence_key}'."],
        }

    try:
        with open(path, "r", encoding="utf-8") as f:
            evidence = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        return {
            "safe_to_continue": False,
            "blockers": [f"Failed to read preflight evidence: {e}"],
        }

    blockers = []

    status = evidence.get("status")
    if status != "passed":
        blockers.append(f"Preflight evidence status is '{status}', expected 'passed'.")

    agent = evidence.get("agent")
    if required_agent and agent != required_agent:
        blockers.append(
            f"Mismatched agent. Required '{required_agent}', but evidence was recorded for '{agent}'."
        )

    timestamp = evidence.get("timestamp", 0)
    current_time = time.time()

    if current_time - timestamp > ttl_seconds:
        blockers.append(
            f"Stale preflight evidence. Evidence is older than {ttl_seconds} seconds."
        )
    elif current_time < timestamp - 60:
        blockers.append("Preflight evidence is from the future (invalid timestamp).")

    if exact_state:
        for k, expected_v in exact_state.items():
            if expected_v is None:
                continue
            actual_v = evidence.get(k)
            if actual_v is None:
                blockers.append(
                    f"Exact state validation failed: missing expected field '{k}'."
                )
            elif str(actual_v) != str(expected_v):
                blockers.append(
                    f"Exact state validation failed for '{k}': expected '{expected_v}', got '{actual_v}'."
                )

    return {"safe_to_continue": len(blockers) == 0, "blockers": blockers}


def verify_preflight_evidence(
    evidence_key: str,
    required_agent: str,
    ttl_seconds: int = 300,
    repo_root: str = ".",
    exact_state: Optional[Dict[str, Any]] = None,
) -> None:
    """Verifies preflight evidence and exits if not safe to continue."""
    import sys

    result = require_safe_preflight(
        evidence_key, required_agent, ttl_seconds, repo_root, exact_state=exact_state
    )
    if not result.get("safe_to_continue"):
        print(
            f"Preflight gate failed for '{evidence_key}' and agent '{required_agent}':",
            file=sys.stderr,
        )
        for blocker in result.get("blockers", []):
            print(f" - {blocker}", file=sys.stderr)
        sys.exit(1)
