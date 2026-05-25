import json
import re
from typing import Any, Dict


class SubagentNoOpError(Exception):
    """Raised when a subagent result is empty or missing required evidence."""

    pass


class SubagentResultGuard:
    @staticmethod
    def validate_result(result_payload: str) -> Dict[str, Any]:
        """
        Validates the subagent result payload.
        The payload can be a JSON string or text containing specific markers.
        """
        if not result_payload or not result_payload.strip():
            raise SubagentNoOpError("Result is empty or whitespace.")

        data = None
        # Try JSON first
        try:
            parsed = json.loads(result_payload)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError:
            pass

        # Fallback to text markers if not valid JSON
        if data is None:
            data = SubagentResultGuard._parse_text_markers(result_payload)

        issue_number = data.get("issue_number") or data.get("issue")
        # Accept integer or string representations of issue numbers
        if not issue_number:
            raise SubagentNoOpError("Result missing required field: issue_number.")

        has_status = bool(
            data.get("status")
            or data.get("validation_status")
            or data.get("validation_evidence")
        )
        has_blocker = bool(data.get("blocker") or data.get("blocker_evidence"))

        if not has_status and not has_blocker:
            raise SubagentNoOpError(
                "Result missing required evidence: must provide status/validation evidence or blocker evidence."
            )

        # Normalize the result to ensure required fields
        return {
            "issue_number": issue_number,
            "status": data.get("status")
            or data.get("validation_status")
            or data.get("validation_evidence"),
            "blocker_evidence": data.get("blocker") or data.get("blocker_evidence"),
            "original_data": data,
        }

    @staticmethod
    def _parse_text_markers(text: str) -> Dict[str, Any]:
        data = {}

        # 1. Issue number: e.g., "Issue: #429" or "Issue number: 429"
        issue_match = re.search(r"(?i)issue(?:\s*number)?:\s*#?(\d+)", text)
        if issue_match:
            data["issue_number"] = int(issue_match.group(1))

        # 2. Status/Validation: e.g., "Status: SUCCESS" or "Validation Evidence: tests passed"
        status_match = re.search(
            r"(?i)(?:status|validation(?:\s*status|\s*evidence)?):\s*([^\n]+)", text
        )
        if status_match:
            data["status"] = status_match.group(1).strip()

        # 3. Blocker evidence: e.g., "Blocker: missing file" or "Blocker Evidence: test failed"
        blocker_match = re.search(r"(?i)blocker(?:\s*evidence)?:\s*([^\n]+)", text)
        if blocker_match:
            data["blocker_evidence"] = blocker_match.group(1).strip()

        if not data:
            raise SubagentNoOpError(
                "Could not parse required JSON or text markers from result."
            )

        return data


if __name__ == "__main__":
    import sys

    payload = sys.stdin.read()
    try:
        SubagentResultGuard.validate_result(payload)
        print("OK")
        sys.exit(0)
    except SubagentNoOpError as e:
        print(f"Subagent No-Op Error: {e}", file=sys.stderr)
        sys.exit(1)
