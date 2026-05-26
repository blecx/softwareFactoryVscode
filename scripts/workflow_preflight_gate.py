import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple


def get_evidence_path(evidence_key: str, repo_root: str = ".") -> str:
    """Returns the path to the evidence file under .tmp/ directory."""
    tmp_dir = os.path.join(repo_root, ".tmp")
    if not os.path.exists(tmp_dir):
        os.makedirs(tmp_dir, exist_ok=True)

    safe_key = "".join(
        c for c in evidence_key if c.isalnum() or c in ("-", "_")
    ).strip()
    if not safe_key:
        safe_key = "default"

    return os.path.join(tmp_dir, f"workflow_preflight_{safe_key}.json")


def _get_schema_path(repo_root: str = ".") -> str:
    return os.path.join(repo_root, "schemas", "workflow-preflight-evidence.schema.json")


def validate_against_schema(
    evidence: Dict[str, Any], repo_root: str = "."
) -> Tuple[bool, list[str]]:
    schema_path = _get_schema_path(repo_root)
    if not os.path.exists(schema_path):
        return False, [f"Schema not found at {schema_path}"]

    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
    except Exception as e:
        return False, [f"Failed to load schema: {e}"]

    try:
        import jsonschema

        jsonschema.validate(instance=evidence, schema=schema)
    except ImportError:
        errors = []
        required = schema.get("required", [])
        for req in required:
            if req not in evidence:
                errors.append(f"Missing required field: {req}")

        allowed_props = set(schema.get("properties", {}).keys())
        for k in evidence.keys():
            if k not in allowed_props:
                errors.append(f"Additional property not allowed: {k}")

        verdict_enum = schema.get("properties", {}).get("verdict", {}).get("enum", [])
        if evidence.get("verdict") not in verdict_enum:
            errors.append(f"Invalid verdict: {evidence.get('verdict')}")

        exact_state_schema = schema.get("properties", {}).get("exact_state", {})
        exact_state = evidence.get("exact_state")
        if exact_state is not None:
            if not isinstance(exact_state, dict):
                errors.append("exact_state must be an object")
            else:
                allowed_es_props = set(exact_state_schema.get("properties", {}).keys())
                for ek in exact_state.keys():
                    if ek not in allowed_es_props:
                        errors.append(
                            f"Additional exact_state property not allowed: {ek}"
                        )

        if errors:
            return False, errors
    except Exception as e:
        return False, [f"Schema validation failed: {str(e)}"]

    return True, []


def record_preflight_evidence(
    evidence_key: str,
    identity: str,
    verdict: str,
    repo_root: str = ".",
    exact_state: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Records workflow preflight evidence into a JSON file under .tmp/
    """
    path = get_evidence_path(evidence_key, repo_root)

    evidence = {
        "identity": identity,
        "verdict": verdict,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if exact_state:
        clean_exact_state = {k: v for k, v in exact_state.items() if v is not None}
        if clean_exact_state:
            evidence["exact_state"] = clean_exact_state

    is_valid, errs = validate_against_schema(evidence, repo_root)
    if not is_valid:
        raise ValueError(f"Failed to generate valid evidence: {errs}")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)


def require_safe_preflight(
    evidence_key: str,
    required_identity: str,
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

    valid_schema, schema_blockers = validate_against_schema(evidence, repo_root)
    if not valid_schema:
        return {"safe_to_continue": False, "blockers": schema_blockers}

    blockers = []

    verdict = evidence.get("verdict")
    if verdict != "pass":
        blockers.append(f"Preflight evidence verdict is '{verdict}', expected 'pass'.")

    identity = evidence.get("identity")
    if required_identity and identity != required_identity:
        blockers.append(
            f"Mismatched identity. Required '{required_identity}', but evidence was recorded for '{identity}'."
        )

    timestamp_str = evidence.get("timestamp")
    try:
        timestamp = datetime.fromisoformat(
            timestamp_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        timestamp = 0

    current_time = time.time()

    if current_time - timestamp > ttl_seconds:
        blockers.append(
            f"Stale preflight evidence. Evidence is older than {ttl_seconds} seconds."
        )
    elif current_time < timestamp - 60:
        blockers.append("Preflight evidence is from the future (invalid timestamp).")

    if exact_state:
        actual_exact_state = evidence.get("exact_state", {})
        for k, expected_v in exact_state.items():
            if expected_v is None:
                continue
            actual_v = actual_exact_state.get(k)
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
    required_identity: str,
    ttl_seconds: int = 300,
    repo_root: str = ".",
    exact_state: Optional[Dict[str, Any]] = None,
) -> None:
    result = require_safe_preflight(
        evidence_key, required_identity, ttl_seconds, repo_root, exact_state=exact_state
    )
    if not result.get("safe_to_continue"):
        print(
            f"Preflight gate failed for '{evidence_key}' and identity '{required_identity}':",
            file=sys.stderr,
        )
        for blocker in result.get("blockers", []):
            print(f" - {blocker}", file=sys.stderr)
        sys.exit(1)
