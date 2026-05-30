#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import jsonschema


def validate_slice(slice_data: dict) -> str:
    # Basic schema validation
    schema_path = (
        Path(__file__).resolve().parent.parent
        / "schemas"
        / "execution-slice-constraints.schema.json"
    )
    with open(schema_path) as f:
        schema = json.load(f)

    try:
        jsonschema.validate(instance=slice_data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        return "hard-blocked"

    target_files = slice_data.get("target_files", [])
    conceptual_domains = slice_data.get("conceptual_domains", [])
    diff_budget = slice_data.get("diff_size_budget_lines", 0)

    if len(target_files) > 5 or len(conceptual_domains) > 1:
        return "hard-blocked"

    if len(target_files) > 3 or (diff_budget and diff_budget > 250):
        return "soft-over-budget"

    return "pass"


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: validate_execution_slice.py <slice.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        data = json.load(f)

    result = validate_slice(data)
    print(result)
    if result == "hard-blocked":
        sys.exit(1)
