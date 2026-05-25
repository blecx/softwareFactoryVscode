import argparse
import json
import os
import sys

try:
    from scripts.workflow_task_classifier import WorkflowTaskClassifier
except ImportError:
    # Fallback for running script directly in scripts/
    from workflow_task_classifier import WorkflowTaskClassifier


def load_and_validate_manifest(manifest_path):
    """
    Loads the routing manifest and validates its schema inline.
    Returns (manifest_data, blockers_list)
    """
    if not os.path.exists(manifest_path):
        return None, [f"Missing routing manifest: {manifest_path}"]

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            routing_manifest = json.load(f)
    except json.JSONDecodeError as e:
        return None, [f"Routing manifest contains invalid JSON: {e}"]
    except Exception as e:
        return None, [f"Failed to load routing manifest: {e}"]

    if not routing_manifest:
        return routing_manifest, ["Routing manifest is empty"]

    if not isinstance(routing_manifest, list):
        return routing_manifest, [
            "Routing manifest schema validation failed: Routing manifest must be a JSON array"
        ]

    schema_blockers = []
    seen_agents = set()
    for i, route in enumerate(routing_manifest):
        if not isinstance(route, dict):
            schema_blockers.append(f"Route[{i}] is not an object")
            continue

        agent = route.get("agent")
        if agent is not None:
            if agent in seen_agents:
                schema_blockers.append(f"Invalid route {agent}: duplicate agent name")
            seen_agents.add(agent)

        missing = []
        for field in ["agent", "task_kinds", "requirements", "human_only"]:
            if field not in route:
                missing.append(field)

        task_kinds = route.get("task_kinds")
        if task_kinds is not None and not task_kinds:
            schema_blockers.append(
                f"Invalid route {agent or f'Route[{i}]'}: task_kinds cannot be empty"
            )

        if missing:
            name = agent or f"Route[{i}]"
            schema_blockers.append(
                f"Invalid route {name}: missing {', '.join(missing)}"
            )

    if schema_blockers:
        return routing_manifest, [
            f"Routing manifest schema validation failed: {'; '.join(schema_blockers)}"
        ]

    return routing_manifest, []


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

    routing_manifest, manifest_blockers = load_and_validate_manifest(target_manifest)
    if manifest_blockers:
        return {
            "safe_to_continue": False,
            "required_agent": c_result.get("required_agent"),
            "blockers": manifest_blockers,
        }

    # Initialize response
    result = {
        "safe_to_continue": True,
        "required_agent": c_result.get("required_agent"),
        "blockers": [],
    }

    if c_result.get("language_config_missing"):
        return {
            "safe_to_continue": False,
            "required_agent": None,
            "blockers": [f"Missing factory workflow language config: {config_path}"],
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
    # (Note: earlier code did this before looking at routing_manifest)
    if c_result.get("task_kind") == "issue":
        result["required_agent"] = "@resolve-issue"

    if not routing_manifest:
        result["safe_to_continue"] = False
        result["blockers"].append("Routing manifest is empty")
        return result

    # Evaluate against routing manifest
    agent_found = False
    for route in routing_manifest:
        if route.get("agent") == result.get("required_agent"):
            agent_found = True
            if route.get("human_only") and not is_human_activated:
                result["safe_to_continue"] = False
                msg = f"{route.get('agent')} requires explicit human evidence."
                if msg not in result["blockers"]:
                    result["blockers"].append(msg)

    if result.get("required_agent") and not agent_found:
        result["safe_to_continue"] = False
        result["blockers"].append(
            f"Required agent '{result.get('required_agent')}' not found in routing manifest."
        )

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
