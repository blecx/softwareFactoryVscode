#!/usr/bin/env python3
"""GitHub access helper with a read-only status command and stable JSON shape."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from typing import Any, Dict, Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from factory_runtime.secret_safety import redact_secret_text


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


def get_git_config(key: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "config", "--get", key], capture_output=True, text=True
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_git_version() -> Tuple[int, int]:
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        parts = result.stdout.strip().split()
        if len(parts) >= 3:
            v_parts = parts[2].split(".")
            return int(v_parts[0]), int(v_parts[1])
    except Exception:
        pass
    return (0, 0)


def probe_ssh_signing() -> Dict[str, str]:
    version = get_git_version()
    if version < (2, 34):
        return {
            "status": "blocked",
            "notes": "Git version below 2.34 does not support SSH signing.",
        }

    signingkey = get_git_config("user.signingkey")
    if not signingkey:
        return {
            "status": "blocked",
            "notes": "user.signingkey is not configured for SSH.",
        }

    return {"status": "ready", "notes": "SSH signing is configured."}


def probe_gpg_signing() -> Dict[str, str]:
    signingkey = get_git_config("user.signingkey")
    if not signingkey:
        return {
            "status": "blocked",
            "notes": "user.signingkey is not configured for GPG.",
        }

    try:
        result = subprocess.run(
            ["gpg", "--list-secret-keys", signingkey],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return {"status": "ready", "notes": "GPG secret key is available."}
        else:
            return {
                "status": "blocked",
                "notes": "GPG secret key not available locally.",
            }
    except Exception:
        return {"status": "blocked", "notes": "gpg command not found or failed."}


def probe_signing() -> Dict[str, Any]:
    priority_str = os.environ.get("FACTORY_GIT_SIGNING_PRIORITY", "ssh,gpg")
    priority_list = [p.strip().lower() for p in priority_str.split(",") if p.strip()]
    if not priority_list:
        priority_list = ["ssh", "gpg"]

    primary = priority_list[0]

    ssh_status = probe_ssh_signing()
    gpg_status = probe_gpg_signing()

    backends = {"ssh": ssh_status, "gpg": gpg_status}

    primary_status = backends.get(
        primary, {"status": "blocked", "notes": "Unknown backend."}
    )
    overall_status = primary_status["status"]

    notes = f"Primary backend '{primary}' is {primary_status['status']}."
    if overall_status == "blocked" and len(priority_list) > 1:
        fallback = priority_list[1]
        fallback_status = backends.get(fallback, {"status": "blocked"})
        notes += f" Fallback backend '{fallback}' is {fallback_status['status']}."

    return {
        "status": overall_status,
        "notes": notes,
        "backends": backends,
        "primary": primary,
    }


def probe_github_api() -> Dict[str, Any]:
    sources = []
    for env_var in ["GITHUB_TOKEN", "GH_TOKEN", "GITHUB_PAT"]:
        if os.environ.get(env_var):
            sources.append(env_var)

    try:
        result = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True
        )

        stdout_redacted = redact_secret_text(result.stdout)
        stderr_redacted = redact_secret_text(result.stderr)

        output = stdout_redacted if stdout_redacted.strip() else stderr_redacted

        if result.returncode == 0:
            notes = "GitHub API is ready."
            if sources:
                notes += f" Sources: {', '.join(sources)}."
            return {"status": "ready", "notes": notes, "details": output.strip()}
        else:
            return {
                "status": "blocked",
                "notes": "GitHub API authentication failed. Please run 'gh auth login' or set GITHUB_TOKEN.",
                "details": output.strip(),
            }
    except FileNotFoundError:
        return {
            "status": "blocked",
            "notes": "'gh' command not found. Please install GitHub CLI or set GITHUB_TOKEN.",
        }
    except Exception as e:
        return {
            "status": "blocked",
            "notes": f"gh auth status failed: {redact_secret_text(str(e))}",
        }


def get_status() -> Dict[str, Any]:
    """Return the placeholder status for GitHub access credential lanes."""
    return {
        "lanes": {
            "git_transport": probe_git_transport(),
            "signing": probe_signing(),
            "github_api": probe_github_api(),
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
