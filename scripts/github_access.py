#!/usr/bin/env python3
"""GitHub access helper with a read-only status command and stable JSON shape."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple


def get_git_remote_url() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def has_ssh_auth_sock() -> bool:
    return "SSH_AUTH_SOCK" in os.environ


def get_ssh_add_status() -> Tuple[bool, str]:
    try:
        result = subprocess.run(["ssh-add", "-l"], capture_output=True, text=True)
        if result.returncode == 0:
            return True, "Keys loaded."
        elif result.returncode == 1:
            return False, "Agent has no keys."
        else:
            return False, f"Could not contact agent: {result.stderr.strip()}"
    except Exception as e:
        return False, f"ssh-add command failed: {e}"


def probe_github_ssh() -> Tuple[bool, str]:
    try:
        result = subprocess.run(
            ["ssh", "-T", "-o", "ConnectTimeout=5", "git@github.com"],
            capture_output=True,
            text=True,
        )
        output = result.stderr + result.stdout
        if "successfully authenticated" in output.lower():
            return True, "Successfully authenticated to GitHub."
        else:
            return False, "SSH connection to GitHub failed."
    except Exception as e:
        return False, f"SSH command failed: {e}"


def probe_git_transport() -> Dict[str, str]:
    remote_url = get_git_remote_url()
    if not remote_url:
        return {"status": "unknown", "notes": "No git remote 'origin' found."}

    if remote_url.startswith("https://"):
        return {
            "status": "action_required",
            "notes": "HTTPS remote detected. Expected SSH. Please change remote URL.",
        }

    if not has_ssh_auth_sock():
        return {
            "status": "blocked",
            "notes": "SSH_AUTH_SOCK is missing. Please forward ssh-agent.",
        }

    has_keys, key_msg = get_ssh_add_status()
    if not has_keys:
        return {"status": "blocked", "notes": f"SSH key check failed: {key_msg}"}

    ssh_ready, ssh_msg = probe_github_ssh()
    if ssh_ready:
        return {"status": "ready", "notes": "SSH transport is ready and authenticated."}
    else:
        return {
            "status": "blocked",
            "notes": "SSH authentication failed. Ensure public key is in GitHub.",
        }


def get_status() -> Dict[str, Any]:
    """Return the placeholder status for GitHub access credential lanes."""
    return {
        "lanes": {
            "git_transport": probe_git_transport(),
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
