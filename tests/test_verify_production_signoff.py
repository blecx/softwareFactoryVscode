import json
import os
import tempfile

import pytest

from scripts.verify_production_signoff import verify_signoff


def test_missing_file():
    result = verify_signoff(".tmp/non-existent-file.json")
    assert not result["valid"]
    assert "No production signoff evidence found" in result["blockers"][0]


def test_invalid_json():
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        f.write("{ not valid json ")
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "is not valid JSON" in result["blockers"][0]
    finally:
        os.unlink(filepath)


def test_missing_required_fields():
    data = {
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        # missing command and evidence
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        blockers = " ".join(result["blockers"])
        assert "Missing required field: 'command'" in blockers
        assert "Missing required field: 'evidence'" in blockers
    finally:
        os.unlink(filepath)


def test_unsuccessful_status():
    data = {
        "command": "run_signoff",
        "status": "failed",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "Signoff status is not success: failed" in result["blockers"]
    finally:
        os.unlink(filepath)


def test_valid_signoff():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True, "implementation": True, "validation": True},
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert result["valid"]
        assert len(result["blockers"]) == 0
    finally:
        os.unlink(filepath)


def test_secret_in_key():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "api_key": "some-value",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert (
            "Key 'api_key' looks like a secret but has unredacted value."
            in result["blockers"]
        )
    finally:
        os.unlink(filepath)


def test_secret_in_value():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "some_data": "ghp_123456789012345678901234567890123456",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert not result["valid"]
        assert "Value at 'some_data' looks like a secret." in result["blockers"]
    finally:
        os.unlink(filepath)


def test_safe_secret_key():
    data = {
        "command": "run_signoff",
        "status": "success",
        "timestamp": "2023-01-01T00:00:00Z",
        "evidence": {"docs": True},
        "api_key": "redacted",
    }
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        json.dump(data, f)
        filepath = f.name

    try:
        result = verify_signoff(filepath)
        assert result["valid"]
    finally:
        os.unlink(filepath)
