import argparse
import json
import os
import sys

try:
    from scripts.workflow_task_classifier import WorkflowTaskClassifier
except ImportError:
    # Fallback for running script directly in scripts/
    from workflow_task_classifier import WorkflowTaskClassifier


def run_preflight(
    request_text,
    is_human_activated,
    manifest_path="manifests/agent-routing-contract.json",
    config_path="configs/workflow_language.yml",
):
    classifier = WorkflowTaskClassifier(config_path=config_path)
    c_result = classifier.classify(request_text, is_human_activated=is_human_activated)

    target_manifest = (
        manifest_path
        if os.path.exists(manifest_path)
        else os.path.join(os.path.dirname(__file__), "..", manifest_path)
    )

    try:
        with open(target_manifest, "r", encoding="utf-8") as f:
            routing_manifest = json.load(f)
    except Exception as e:
        routing_manifest = []

    # Initialize response
    result = {
        "safe_to_continue": True,
        "required_agent": c_result.get("required_agent"),
        "blockers": [],
    }

    # Reject bypass without human-only evidence
    if c_result.get("task_kind") == "bypass" and not is_human_activated:
        result["safe_to_continue"] = False
        if "Bypass requires explicit human evidence." not in result["blockers"]:
            result["blockers"].append("Bypass requires explicit human evidence.")

    # Reject unknown or ambiguous task kinds
    if c_result.get("clarification_flag") or c_result.get("task_kind") == "unknown":
        result["safe_to_continue"] = False
        msg = c_result.get("clarification_message", "Unknown or ambiguous task kind.")
        if msg not in result["blockers"]:
            result["blockers"].append(msg)

    # Map explicit issue request to resolve-issue route
    if c_result.get("task_kind") == "issue":
        result["required_agent"] = "@resolve-issue"

    # Evaluate against routing manifest
    for route in routing_manifest:
        if route.get("agent") == result.get("required_agent"):
            if route.get("human_only") and not is_human_activated:
                result["safe_to_continue"] = False
                msg = f"{route.get('agent')} requires explicit human evidence."
                if msg not in result["blockers"]:
                    result["blockers"].append(msg)

    return result


def main():
    parser = argparse.ArgumentParser(description="Workflow Preflight")
    parser.add_argument("--request", required=True, help="Operator request text")
    parser.add_argument(
        "--human", action="store_true", help="Explicit human activation"
    )
    parser.add_argument(
        "--manifest",
        default="manifests/agent-routing-contract.json",
        help="Path to routing manifest",
    )
    parser.add_argument(
        "--config",
        default="configs/workflow_language.yml",
        help="Path to workflow language config",
    )
    args = parser.parse_args()

    result = run_preflight(args.request, args.human, args.manifest, args.config)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
