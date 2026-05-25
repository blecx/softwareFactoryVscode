import json
import os
import time
from typing import Any, Dict


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
    evidence_key: str, agent: str, status: str, repo_root: str = "."
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

    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)


def require_safe_preflight(
    evidence_key: str, required_agent: str, ttl_seconds: int = 300, repo_root: str = "."
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

    return {"safe_to_continue": len(blockers) == 0, "blockers": blockers}


def verify_preflight_evidence(
    evidence_key: str, required_agent: str, ttl_seconds: int = 300, repo_root: str = "."
) -> None:
    """Verifies preflight evidence and exits if not safe to continue."""
    import sys

    result = require_safe_preflight(
        evidence_key, required_agent, ttl_seconds, repo_root
    )
    if not result.get("safe_to_continue"):
        print(
            f"Preflight gate failed for '{evidence_key}' and agent '{required_agent}':",
            file=sys.stderr,
        )
        for blocker in result.get("blockers", []):
            print(f" - {blocker}", file=sys.stderr)
        sys.exit(1)
