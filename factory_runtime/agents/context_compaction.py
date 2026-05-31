import json
from typing import Any


def compact_context_packet(packet: dict[str, Any], max_chars: int = 16000) -> str:
    """Summarizes or trims a context packet to fit within a given budget.
    Raises ValueError if it cannot be compacted within budget.
    """
    raw = json.dumps(packet, indent=2)
    if len(raw) <= max_chars:
        return raw

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

    # If it is still too large, it is out of budget bounds.
    # Return an error to prevent context window explosion or broken JSON.
    raise ValueError(
        f"Context packet size ({len(raw)} chars) exceeds context budget limit of {max_chars} chars."
    )
