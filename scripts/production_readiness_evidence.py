#!/usr/bin/env python3
import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

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
    ci_evidence: Optional[Dict[str, Any]] = None,
    strict_verification: bool = False,
    repo: Optional[str] = None,
) -> Dict[str, Any]:
    blockers = []
    authoritative = False

    if ci_evidence is not None:
        signoff_result = verify_ci_evidence(
            ci_evidence, repo=repo, strict=strict_verification
        )
        source = "github-ci"
        authoritative = True

        # Inject computed streak evidence
        from verify_production_signoff import (
            CANONICAL_PRODUCTION_JOBS,
            fetch_github_history,
        )

        try:
            branch = ci_evidence.get("branch")
            workflow_name = ci_evidence.get("workflow_name")
            head_sha = ci_evidence.get("head_sha")

            if branch and workflow_name and head_sha:
                history = fetch_github_history(
                    branch, workflow_name, repo=repo, strict=strict_verification
                )
                # Convert back to dict for score_readiness to parse if needed
                history_dicts = []
                for h in history:
                    history_dicts.append(
                        {
                            "run_id": h.run_id,
                            "branch": h.branch,
                            "head_sha": h.head_sha,
                            "status": h.status,
                            "conclusion": h.conclusion,
                            "jobs": [
                                {"name": j.name, "conclusion": j.conclusion}
                                for j in h.jobs
                            ],
                        }
                    )

                review_input["green_streak_evidence"] = {
                    "history": history_dicts,
                    "target_branch": branch,
                    "target_sha": head_sha,
                    "required_jobs": (
                        CANONICAL_PRODUCTION_JOBS if strict_verification else []
                    ),
                }
            elif strict_verification:
                missing = [
                    f
                    for f in ["branch", "workflow_name", "head_sha"]
                    if not ci_evidence.get(f)
                ]
                blockers.append(
                    f"Missing required fields for authoritative history: {', '.join(missing)}"
                )
        except Exception as e:
            if strict_verification:
                blockers.append(str(e))
            else:
                pass
    else:
        signoff_result = verify_signoff(
            signoff_filepath, repo=repo, strict=strict_verification
        )
        source = "local-file"
        authoritative = False

    if strict_verification and not authoritative:
        blockers.append("GitHub verification is missing in authoritative mode.")

    score_result = score_readiness(review_input, strict=strict_verification)

    blockers.extend(signoff_result.get("blockers", []))
    blockers.extend(score_result.get("blockers", []))

    references = {
        "source": source,
        "authoritative": authoritative,
        "mode": "strict" if strict_verification else "offline/fixture",
    }
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


def main(argv=None):
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
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Explicit repository (e.g. owner/repo) to verify against",
    )
    parser.add_argument(
        "--strict-verification",
        action="store_true",
        help="Enforce authoritative mode for CI evidence",
    )
    args = parser.parse_args(argv)

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

    result = aggregate_evidence(
        input_data,
        args.signoff_file,
        ci_evidence_data,
        strict_verification=args.strict_verification,
        repo=args.repo,
    )
    print(json.dumps(result, indent=2))

    if not result["ready"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
