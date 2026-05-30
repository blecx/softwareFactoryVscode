#!/usr/bin/env python3
"""GitHub access helper with a read-only status command and stable JSON shape."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict


def get_status() -> Dict[str, Any]:
    """Return the placeholder status for GitHub access credential lanes."""
    return {
        "lanes": {
            "git_transport": {
                "status": "unknown",
                "notes": "Detailed probe pending (ADR-019 SSH remote default)",
            },
            "signing": {
                "status": "unknown",
                "notes": "Detailed probe pending (ADR-019 ssh/gpg priority)",
            },
            "github_api": {
                "status": "unknown",
                "notes": "Detailed probe pending (ADR-019 token/App isolation)",
            },
        }
    }


def cmd_status(args: argparse.Namespace) -> int:
    """Handle the status subcommand."""
    status_data = get_status()

    if args.json:
        print(json.dumps(status_data, indent=2))
        return 0

    print("GitHub Access Status (Skeleton)")
    print("===============================")
    for lane_name, lane_info in status_data["lanes"].items():
        print(f"Lane: {lane_name}")
        print(f"  Status: {lane_info['status']}")
        print(f"  Notes : {lane_info['notes']}")
        print()
    print("Note: Detailed probes for each lane will land in follow-up issues.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="GitHub access helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status", help="Show GitHub access status.")
    status_parser.add_argument(
        "--json", action="store_true", help="Output status in JSON format."
    )

    args = parser.parse_args()

    if args.command == "status":
        return cmd_status(args)

    return 1


if __name__ == "__main__":
    sys.exit(main())
