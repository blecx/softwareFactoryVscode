#!/usr/bin/env python3
import json
import os
import re
import sys
from typing import Any, Dict, List

DEFAULT_SIGN_OFF_FILE = ".tmp/production-readiness/latest.json"

SECRET_PATTERNS = [
    re.compile(r"gh[posura]_[a-zA-Z0-9_]{36,}"),
    re.compile(r"sk-[a-zA-Z0-9_]{40,}"),
    re.compile(r"ey[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # JWT
]

SECRET_KEY_WORDS = ["secret", "token", "password", "api_key", "apikey"]


def contains_secret(val: Any) -> bool:
    if isinstance(val, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(val):
                return True
    return False


def check_dict_for_secrets(data: Dict[str, Any], path: str = "") -> List[str]:
    violations = []
    if not isinstance(data, dict):
        return violations

    for k, v in data.items():
        current_path = f"{path}.{k}" if path else k

        # Check if key implies a secret
        if any(word in k.lower() for word in SECRET_KEY_WORDS):
            # If it's a non-empty string that isn't a safe placeholder
            if (
                isinstance(v, str)
                and len(v) > 0
                and v.lower() not in ["hidden", "redacted", "xxx"]
            ):
                violations.append(
                    f"Key '{current_path}' looks like a secret but has unredacted value."
                )

        if contains_secret(v):
            violations.append(f"Value at '{current_path}' looks like a secret.")

        if isinstance(v, dict):
            violations.extend(check_dict_for_secrets(v, current_path))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                list_path = f"{current_path}[{i}]"
                if isinstance(item, dict):
                    violations.extend(check_dict_for_secrets(item, list_path))
                elif contains_secret(item):
                    violations.append(f"Value at '{list_path}' looks like a secret.")
    return violations


def verify_signoff(filepath: str) -> Dict[str, Any]:
    if not os.path.exists(filepath):
        return {
            "valid": False,
            "blockers": [
                f"No production signoff evidence found at {filepath}. Please generate production-readiness evidence first."
            ],
        }

    try:
        with open(filepath, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {"valid": False, "blockers": [f"File {filepath} is not valid JSON."]}

    blockers = []
    required_fields = ["command", "status", "timestamp", "evidence"]
    for field in required_fields:
        if field not in data:
            blockers.append(f"Missing required field: '{field}'")

    if "status" in data and data["status"] != "success":
        blockers.append(f"Signoff status is not success: {data['status']}")

    secret_violations = check_dict_for_secrets(data)
    blockers.extend(secret_violations)

    return {"valid": len(blockers) == 0, "blockers": blockers}


def main():
    filepath = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SIGN_OFF_FILE
    result = verify_signoff(filepath)
    if not result["valid"]:
        print("Production signoff verification failed:")
        for blocker in result["blockers"]:
            print(f" - {blocker}")
        sys.exit(1)

    print("Production signoff evidence is valid.")
    sys.exit(0)


if __name__ == "__main__":
    main()
