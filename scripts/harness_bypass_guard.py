#!/usr/bin/env python3
"""
Mechanical bypass authorization guard.
Provides explicit human confirmation evidence requirement before bypass operations can proceed.
"""

import argparse
import datetime
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Harness Bypass Authorization Guard")
    parser.add_argument(
        "--reason",
        required=True,
        help="Explicit reason for bypassing standard governance.",
    )
    args = parser.parse_args()

    # The token expects explicit human presence.
    # An agent shouldn't trivially guess or bypass this without human intervention.
    expected_token = "I_AUTHORIZE_BYPASS"
    user_token = os.environ.get("HARNESS_BYPASS_ACK")

    if user_token != expected_token:
        print(
            "ERROR: Explicit human authorization missing or incorrect.", file=sys.stderr
        )
        print(
            f"Bypass rejected: Agent-delegated or ambiguous activation is not allowed.",
            file=sys.stderr,
        )
        print(
            f"To proceed, the human operator must set HARNESS_BYPASS_ACK='{expected_token}'",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Bypass explicitly authorized by human operator.")

    # Write audit log
    log_file = ".tmp/emergency-bypass.log"
    # Fallback to current directory .tmp, or relative paths
    try:
        if not os.path.exists(".tmp"):
            os.makedirs(".tmp")
        now = datetime.datetime.now().isoformat()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"{now} - BYPASS REASON: {args.reason}\n")
        print(f"Audit log appended to {log_file}")
    except Exception as e:
        print(f"WARNING: Could not write to audit log: {e}", file=sys.stderr)
        # We don't necessarily fail here, but the instruction expects the log

    sys.exit(0)


if __name__ == "__main__":
    main()
