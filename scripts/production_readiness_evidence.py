#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from production_readiness_score import score_readiness
from verify_production_signoff import (
    DEFAULT_SIGN_OFF_FILE,
    verify_ci_evidence,
    verify_signoff,
)


def aggregate_evidence(
    review_input: Dict[str, Any],
    signoff_filepath: str,
    ci_evidence: Dict[str, Any] = None,
) -> Dict[str, Any]:
    if ci_evidence is not None:
        signoff_result = verify_ci_evidence(ci_evidence)
        source = "github-ci"
    else:
        signoff_result = verify_signoff(signoff_filepath)
        source = "local-file"

    score_result = score_readiness(review_input)

    blockers = []
    blockers.extend(signoff_result.get("blockers", []))
    blockers.extend(score_result.get("blockers", []))

    references = {"source": source}
    if source == "local-file":
        references["signoff_file"] = signoff_filepath
    else:
        references["ci_evidence"] = ci_evidence

    return {
        "ready": len(blockers) == 0,
        "blockers": blockers,
        "signoff_valid": signoff_result.get("valid", False),
        "score_readiness": score_result,
        "references": references,
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
    parser.add_argument(
        "--ci-evidence",
        type=str,
        default=None,
        help="JSON string or file path containing CI evidence",
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

    ci_evidence_data = None
    if args.ci_evidence:
        try:
            try:
                with open(args.ci_evidence, "r") as f:
                    ci_evidence_data = json.load(f)
            except (FileNotFoundError, OSError):
                ci_evidence_data = json.loads(args.ci_evidence)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON CI evidence: {e}"}))
            sys.exit(1)

    result = aggregate_evidence(input_data, args.signoff_file, ci_evidence_data)
    print(json.dumps(result, indent=2))

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
