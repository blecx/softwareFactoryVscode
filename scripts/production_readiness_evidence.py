#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production_readiness_score import score_readiness
from verify_production_signoff import DEFAULT_SIGN_OFF_FILE, verify_signoff


def aggregate_evidence(
    review_input: Dict[str, Any], signoff_filepath: str
) -> Dict[str, Any]:
    signoff_result = verify_signoff(signoff_filepath)
    score_result = score_readiness(review_input)

    blockers = []
    blockers.extend(signoff_result.get("blockers", []))
    blockers.extend(score_result.get("blockers", []))

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "signoff_valid": signoff_result.get("valid", False),
        "score_readiness": score_result,
        "references": {"signoff_file": signoff_filepath},
    }


def main():
    parser = argparse.ArgumentParser(
        description="Production Readiness Evidence Aggregate Command"
    )
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="JSON string or file path containing review input",
    )
    parser.add_argument(
        "--signoff-file",
        type=str,
        default=DEFAULT_SIGN_OFF_FILE,
        help="Path to production signoff JSON file",
    )
    args = parser.parse_args()

    try:
        try:
            with open(args.input, "r") as f:
                input_data = json.load(f)
        except (FileNotFoundError, OSError):
            input_data = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON input: {e}"}))
        sys.exit(1)

    result = aggregate_evidence(input_data, args.signoff_file)
    print(json.dumps(result, indent=2))

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
