import argparse
import json
import re
import sys


class WorkflowTaskClassifier:
    def __init__(self):
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
            (r"(?i)@harness-bypass-resolution", "bypass", "@harness-bypass-resolution"),
        ]

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
            return result

        if "@harness-bypass-resolution" in request_text:
            if not is_human_activated:
                result["task_kind"] = "bypass"
                result["blocked"] = True
                result["clarification_flag"] = True
                return result
            else:
                result["task_kind"] = "bypass"
                result["confidence"] = 1.0
                result["required_agent"] = "@harness-bypass-resolution"
                result["clarification_flag"] = False
                result["blocked"] = False
                return result

        best_match = None
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
