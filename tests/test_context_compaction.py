from typing import Any

from factory_runtime.agents.context_compaction import compact_context_packet


def test_compact_context_packet_small():
    packet = {"run": {"issue_number": 638, "repo": "test"}}
    res = compact_context_packet(packet, max_chars=4000)
    assert "[CONTENT TRUNCATED" not in res
    assert "issue_number" in res


def test_compact_context_packet_large():
    packet = {"run": {"issue_number": 638, "repo": "test", "huge_logs": "x" * 20000}}
    res = compact_context_packet(packet, max_chars=4000)
    assert len(res) <= 4100  # allowing some margin for the truncation marker
    assert "[CONTENT TRUNCATED" in res
