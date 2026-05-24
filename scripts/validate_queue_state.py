#!/usr/bin/env python3
"""
Validates a queue checkpoint JSON file against the github-issue-queue-state JSON schema.
"""
import argparse
import json
import sys
from pathlib import Path

import jsonschema

SCHEMA_PATH = (
    Path(__file__).parent.parent / "schemas" / "github-issue-queue-state.schema.json"
)


def validate_queue_state(data: dict) -> None:
    try:
        with open(SCHEMA_PATH) as f:
            schema = json.load(f)
    except Exception as e:
        print(f"Error loading schema: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        print(f"Validation error: {e.message}", file=sys.stderr)
        print(f"Schema path: {e.json_path}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Validate queue state JSON")
    parser.add_argument(
        "file", type=Path, help="Path to the JSON state file to validate"
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(args.file) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    validate_queue_state(data)
    print("Queue state is valid.")


if __name__ == "__main__":
    main()
