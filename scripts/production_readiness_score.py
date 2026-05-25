import argparse
import json
import sys
from typing import Any, Dict


def score_readiness(input_data: Dict[str, Any]) -> Dict[str, Any]:
    blockers = []

    # 1. Fail when ADR-013 is missing
    if "ADR-013" not in input_data.get("adrs", []):
        blockers.append("Missing ADR-013 from review input.")

    # 2. Reject docs-only assessments
    evidence = input_data.get("evidence", {})
    has_docs = evidence.get("docs", False)
    has_implementation = evidence.get("implementation", False)
    has_validation = evidence.get("validation", False)

    if has_docs and not (has_implementation or has_validation):
        blockers.append("Rejected docs-only readiness scoring.")

    if not has_implementation:
        blockers.append("Missing implementation evidence.")

    if not has_validation:
        blockers.append("Missing validation evidence.")

    traceability = input_data.get("traceability", {})
    if len(traceability) < 9:
        blockers.append("Missing one or more of the 9 blocking requirements evidence.")
    for key, value in traceability.items():
        if isinstance(value, str) and value.lower() == "evidence gap":
            blockers.append(f"Traceability row {key} still says Evidence gap.")

    if not input_data.get("signoff_evidence"):
        blockers.append("Missing signoff evidence pointer/verifier output.")

    input_score = {
        "adrs_present": len(input_data.get("adrs", [])),
        "docs": has_docs,
        "implementation": has_implementation,
        "validation": has_validation,
    }

    result = {
        "score_inputs": input_score,
        "blockers": blockers,
        "ready": len(blockers) == 0,
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="Production Readiness Score Checker")
    parser.add_argument(
        "--input",
        "-i",
        type=str,
        required=True,
        help="JSON string or file path containing review input",
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

    result = score_readiness(input_data)
    print(json.dumps(result, indent=2))

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
