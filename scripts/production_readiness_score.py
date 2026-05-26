import argparse
import json
import sys
from typing import Any, Dict


def score_readiness(input_data: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
    blockers = []

    # 1. Fail when ADR-013 is missing
    if "ADR-013" not in input_data.get("adrs", []):
        blockers.append("Missing ADR-013 from review input.")

    # 2. Reject docs-only assessments
    evidence = input_data.get("evidence", {})
    has_docs = evidence.get("docs", False)
    has_implementation = evidence.get("implementation", False)
    has_validation = evidence.get("validation", False)

    docs_anchors = input_data.get("docs_anchors", [])

    if strict and not docs_anchors:
        blockers.append("Authoritative readiness requires explicit docs anchors.")

    if not docs_anchors:
        has_docs = False

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

    green_streak_count = 0
    if not strict:
        green_streak_count = input_data.get("green_streak_count", 0)

    streak_evidence = input_data.get("green_streak_evidence")
    if streak_evidence:
        try:
            # We import here to avoid circular imports if any, and access the helper
            from verify_production_signoff import (
                JobEvidence,
                NormalizedRunEvidence,
                compute_green_streak,
            )

            history = []
            for item in streak_evidence.get("history", []):
                jobs = [
                    JobEvidence(
                        name=j.get("name", ""), conclusion=j.get("conclusion", "")
                    )
                    for j in item.get("jobs", [])
                ]
                history.append(
                    NormalizedRunEvidence(
                        run_id=str(item.get("run_id", "")),
                        branch=str(item.get("branch", "")),
                        head_sha=str(item.get("head_sha", "")),
                        status=str(item.get("status", "")),
                        conclusion=str(item.get("conclusion", "")),
                        jobs=jobs,
                    )
                )
            computed_streak, computed_blockers = compute_green_streak(
                history,
                streak_evidence.get("target_branch", ""),
                streak_evidence.get("target_sha", ""),
                streak_evidence.get("required_jobs", []),
            )
            green_streak_count = computed_streak
            blockers.extend(computed_blockers)
        except Exception as e:
            blockers.append(f"Failed to compute green streak: {e}")

    if strict and not streak_evidence:
        blockers.append(
            "Authoritative readiness requires computed GitHub streak evidence, but none was provided."
        )

    if green_streak_count < 3:
        blockers.append("Production gate requires 3 consecutive clean signoff runs.")

    input_score = {
        "adrs_present": len(input_data.get("adrs", [])),
        "docs_anchors_present": len(docs_anchors),
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Run strict mode for authoritative readiness binding.",
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

    result = score_readiness(input_data, strict=args.strict)
    print(json.dumps(result, indent=2))

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
