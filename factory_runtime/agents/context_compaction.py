import json
from typing import Any


def compact_context_packet(packet: dict[str, Any], max_chars: int = 16000) -> str:
    """Summarizes or trims a context packet to fit within a given budget."""
    raw = json.dumps(packet, indent=2)
    if len(raw) <= max_chars:
        return raw

    # Strategy: trim lower-priority fields explicitly (like file contents if too large)
    # We create a shallow copy to manipulate
    compact = dict(packet)

    # 1. Try removing plan feedback if any
    if (
        "plan" in compact
        and isinstance(compact["plan"], dict)
        and "feedback" in compact["plan"]
    ):
        compact["plan"] = dict(compact["plan"])
        compact["plan"]["feedback"] = "(Feedback omitted due to context size limits)"

        raw = json.dumps(compact, indent=2)
        if len(raw) <= max_chars:
            return raw

    # 2. Add an explicit error if it's still too large so it gets blocked or handled
    # But wait, issue says "summarized/trimmed or blocked before request creation"
    # To truly truncate, we might just truncate the raw string.
    raw = json.dumps(compact, indent=2)
    if len(raw) > max_chars:
        half = max_chars // 2
        return (
            raw[:half]
            + "\n\n... [CONTENT TRUNCATED DUE TO CONTEXT WINDOW LIMIT] ...\n\n"
            + raw[-half:]
        )

    return raw
