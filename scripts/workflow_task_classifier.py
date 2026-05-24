import argparse
import json
import os
import re
import sys

import yaml


class WorkflowTaskClassifier:
    def __init__(self, config_path="configs/workflow_language.yml"):
        self.rules = [
            (r"(?i)resolve (an )?issue|work on issue", "issue", "default"),
            (
                r"(?i)merge (the )?pr|execute pr merge|merge pull request",
                "pr_merge",
                "default",
            ),
            (
                r"(?i)execute (the )?approved plan|run approved plan",
                "approved_plan",
                "default",
            ),
            (
                r"(?i)ready for production|production read(?:y|iness)",
                "production_readiness",
                "default",
            ),
            (r"(?i)@harness-bypass-resolution", "bypass", "@harness-bypass-resolution"),
        ]
        self.term_metadata = {}
        target_path = (
            config_path
            if os.path.exists(config_path)
            else os.path.join(os.path.dirname(__file__), "..", config_path)
        )
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                for term in data.get("terms", []):
                    self.term_metadata[term["term_id"]] = term
        except Exception:
            pass

    def classify(self, request_text, is_human_activated=False):
        # Default fallback
        result = {
            "task_kind": "unknown",
            "confidence": 0.0,
            "required_agent": None,
            "clarification_flag": True,
            "blocked": False,
        }

        # Check for bypass
        if (
            "bypass" in request_text.lower()
            and "@harness-bypass-resolution" not in request_text
        ):
            result["task_kind"] = "bypass"
            result["blocked"] = True
            result["clarification_flag"] = True
            if "bypass" in self.term_metadata:
                result["clarification_message"] = self.term_metadata["bypass"].get(
                    "ambiguity_action", ""
                )
            return result

        if "@harness-bypass-resolution" in request_text:
            if not is_human_activated:
                result["task_kind"] = "bypass"
                result["blocked"] = True
                result["clarification_flag"] = True
                if "bypass" in self.term_metadata:
                    result["clarification_message"] = self.term_metadata["bypass"].get(
                        "ambiguity_action", ""
                    )
                return result
            else:
                result["task_kind"] = "bypass"
                result["confidence"] = 1.0
                result["required_agent"] = "@harness-bypass-resolution"
                result["clarification_flag"] = False
                result["blocked"] = False
                return result

        # Check for stale/ambiguous continuation mapping to recovery
        if re.search(r"(?i)continue from last time|stale continuation", request_text):
            result["task_kind"] = "recovery"
            result["clarification_flag"] = True
            if "approved_plan" in self.term_metadata:
                result["clarification_message"] = self.term_metadata[
                    "approved_plan"
                ].get("ambiguity_action", "")
            return result

        yaml_mapping = {
            "approved_plan": "approved_plan",
            "production_readiness_claim": "production_readiness",
            "readiness_projection": "production_readiness",
            "issue_slice": "issue",
        }

        best_match = None
        is_vague = False
        vague_term_id = None

        # Check term phrases from yaml
        for term_id, term_data in self.term_metadata.items():
            if term_id not in yaml_mapping:
                continue
            kind = yaml_mapping[term_id]
            for phrase in term_data.get("allowed_phrases", []):
                if re.search(rf"(?i)\b{re.escape(phrase)}\b", request_text):
                    # Flag single ambiguous words
                    if len(phrase.split()) == 1 and phrase.lower() in [
                        "plan",
                        "continue",
                        "ready",
                    ]:
                        is_vague = True
                        vague_term_id = term_id
                    else:
                        best_match = (kind, "default")
                    break
            if best_match:
                break

        # Fallback to older regex rules
        if not best_match:
            for pattern, kind, default_agent in self.rules:
                if re.search(pattern, request_text):
                    best_match = (kind, default_agent)
                    break

        if best_match:
            result["task_kind"] = best_match[0]
            result["confidence"] = 0.9
            result["required_agent"] = best_match[1]
            result["clarification_flag"] = False
            return result

        if is_vague and vague_term_id:
            result["task_kind"] = "unknown"
            result["clarification_flag"] = True
            evidence = self.term_metadata[vague_term_id].get("ambiguity_action")
            if evidence:
                result["clarification_message"] = evidence
            return result

        return result


def main():
    parser = argparse.ArgumentParser(description="Workflow Task Classifier")
    parser.add_argument("--request", required=True, help="Operator request text")
    parser.add_argument(
        "--human", action="store_true", help="Explicit human activation"
    )
    args = parser.parse_args()

    classifier = WorkflowTaskClassifier()
    result = classifier.classify(args.request, is_human_activated=args.human)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
