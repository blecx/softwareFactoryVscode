#!/usr/bin/env python3
"""Manage Step 2 backend execution queue readiness labels.

This script enforces queue governance for issues #613-#622 in
`YOUR_ORG/YOUR_REPO`:

- exactly one OPEN issue is `status:ready` (the first OPEN in queue order)
- all later OPEN issues are `status:blocked`
- all queue issues and tracker issue #623 carry `track:step2-backend`
- optional tracker checklist sync based on actual issue state

Usage:
  ./scripts/step2_backend_queue.py --dry-run
  ./scripts/step2_backend_queue.py --apply --sync-tracker
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

REPO = os.environ.get("TARGET_REPO", "YOUR_ORG/YOUR_REPO")
QUEUE = [613, 614, 615, 616, 617, 618, 619, 620, 621, 622]
TRACKER_ISSUE = 623

READY_LABEL = "status:ready"
BLOCKED_LABEL = "status:blocked"
TRACK_LABEL = "track:step2-backend"

DEFAULT_SLEEP_SECONDS = 1.0


_last_gh_call_monotonic: float | None = None


def _throttle(sleep_seconds: float) -> None:
    global _last_gh_call_monotonic
    if sleep_seconds <= 0:
        return
    now = time.monotonic()
    if _last_gh_call_monotonic is not None:
        elapsed = now - _last_gh_call_monotonic
        if elapsed < sleep_seconds:
            time.sleep(sleep_seconds - elapsed)
    _last_gh_call_monotonic = time.monotonic()


@dataclass
class IssueState:
    number: int
    state: str
    labels: set[str]

    @property
    def is_open(self) -> bool:
        return self.state.upper() == "OPEN"


def _run_gh_json(args: list[str], sleep_seconds: float) -> Any:
    _throttle(sleep_seconds)
    cmd = ["gh", *args]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as exc:
        message = exc.output.decode("utf-8", errors="replace").strip()
        raise RuntimeError(message or f"gh command failed: {' '.join(cmd)}") from exc

    raw = out.decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    return json.loads(raw)


def _run_gh(args: list[str], sleep_seconds: float) -> None:
    _throttle(sleep_seconds)
    cmd = ["gh", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(msg or f"gh command failed: {' '.join(cmd)}")


def _read_issue(number: int, sleep_seconds: float) -> IssueState:
    data = _run_gh_json(
        ["issue", "view", str(number), "--repo", REPO, "--json", "state,labels"],
        sleep_seconds=sleep_seconds,
    )
    labels = {entry["name"] for entry in data.get("labels", [])}
    return IssueState(number=number, state=str(data.get("state", "")), labels=labels)


def _ensure_label_exists(name: str, sleep_seconds: float) -> None:
    data = _run_gh_json(
        ["label", "list", "--repo", REPO, "--limit", "300", "--json", "name"],
        sleep_seconds=sleep_seconds,
    )
    names = {entry.get("name", "") for entry in (data or [])}
    if name not in names:
        raise RuntimeError(
            f"Required label missing: {name}. Create it before applying."
        )


def _desired_status(number: int, first_open: int | None) -> str | None:
    if first_open is None:
        return None
    if number == first_open:
        return READY_LABEL
    return BLOCKED_LABEL


def _sync_tracker_checklist(
    issue_states: dict[int, IssueState],
    apply: bool,
    sleep_seconds: float,
) -> list[str]:
    body = _run_gh_json(
        ["issue", "view", str(TRACKER_ISSUE), "--repo", REPO, "--json", "body"],
        sleep_seconds=sleep_seconds,
    ).get("body", "")
    lines = body.splitlines()
    updates = 0

    pattern = re.compile(r"^- \[[ xX]\] (#\d+) (.+)$")
    for idx, line in enumerate(lines):
        match = pattern.match(line)
        if not match:
            continue
        number_text = match.group(1)
        title_tail = match.group(2)
        try:
            number = int(number_text.lstrip("#"))
        except ValueError:
            continue
        if number not in issue_states:
            continue
        checked = "x" if not issue_states[number].is_open else " "
        new_line = f"- [{checked}] #{number} {title_tail}"
        if new_line != line:
            lines[idx] = new_line
            updates += 1

    messages: list[str] = []
    if updates == 0:
        messages.append("tracker-checklist: no changes")
        return messages

    messages.append(f"tracker-checklist: {updates} line(s) updated")
    if apply:
        _run_gh(
            [
                "issue",
                "edit",
                str(TRACKER_ISSUE),
                "--repo",
                REPO,
                "--body",
                "\n".join(lines),
            ],
            sleep_seconds=sleep_seconds,
        )
        messages.append("tracker-checklist: applied")
    else:
        messages.append("tracker-checklist: dry-run")
    return messages


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Enforce Step 2 backend queue labels")
    parser.add_argument("--apply", action="store_true", help="Apply label/body changes")
    parser.add_argument(
        "--sync-tracker",
        action="store_true",
        help="Sync tracker checklist with issue state",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Show intended changes without writing"
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Return non-zero when drift is detected (use with dry-run in CI)",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Minimum delay between GitHub CLI requests (default: 1.0)",
    )
    args = parser.parse_args(argv)

    apply = args.apply and not args.dry_run
    sleep_seconds = max(0.0, args.sleep_seconds)

    try:
        _ensure_label_exists(READY_LABEL, sleep_seconds=sleep_seconds)
        _ensure_label_exists(BLOCKED_LABEL, sleep_seconds=sleep_seconds)
        _ensure_label_exists(TRACK_LABEL, sleep_seconds=sleep_seconds)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    issue_states = {
        number: _read_issue(number, sleep_seconds=sleep_seconds) for number in QUEUE
    }

    first_open = next(
        (number for number in QUEUE if issue_states[number].is_open), None
    )

    print(f"Repository: {REPO}")
    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Throttle: {sleep_seconds:.2f}s between GitHub requests")
    print(f"First OPEN issue in queue: {first_open if first_open else 'none'}")

    planned_changes: list[str] = []
    drift_detected = False

    for number in QUEUE:
        current = issue_states[number]
        desired_status = (
            _desired_status(number, first_open) if current.is_open else None
        )

        if TRACK_LABEL not in current.labels:
            planned_changes.append(f"#{number}: add {TRACK_LABEL}")
            drift_detected = True
            if apply:
                _run_gh(
                    [
                        "issue",
                        "edit",
                        str(number),
                        "--repo",
                        REPO,
                        "--add-label",
                        TRACK_LABEL,
                    ],
                    sleep_seconds=sleep_seconds,
                )

        if current.is_open:
            if desired_status == READY_LABEL:
                if READY_LABEL not in current.labels:
                    planned_changes.append(f"#{number}: add {READY_LABEL}")
                    drift_detected = True
                    if apply:
                        _run_gh(
                            [
                                "issue",
                                "edit",
                                str(number),
                                "--repo",
                                REPO,
                                "--add-label",
                                READY_LABEL,
                            ],
                            sleep_seconds=sleep_seconds,
                        )
                if BLOCKED_LABEL in current.labels:
                    planned_changes.append(f"#{number}: remove {BLOCKED_LABEL}")
                    drift_detected = True
                    if apply:
                        _run_gh(
                            [
                                "issue",
                                "edit",
                                str(number),
                                "--repo",
                                REPO,
                                "--remove-label",
                                BLOCKED_LABEL,
                            ],
                            sleep_seconds=sleep_seconds,
                        )
            elif desired_status == BLOCKED_LABEL:
                if BLOCKED_LABEL not in current.labels:
                    planned_changes.append(f"#{number}: add {BLOCKED_LABEL}")
                    drift_detected = True
                    if apply:
                        _run_gh(
                            [
                                "issue",
                                "edit",
                                str(number),
                                "--repo",
                                REPO,
                                "--add-label",
                                BLOCKED_LABEL,
                            ],
                            sleep_seconds=sleep_seconds,
                        )
                if READY_LABEL in current.labels:
                    planned_changes.append(f"#{number}: remove {READY_LABEL}")
                    drift_detected = True
                    if apply:
                        _run_gh(
                            [
                                "issue",
                                "edit",
                                str(number),
                                "--repo",
                                REPO,
                                "--remove-label",
                                READY_LABEL,
                            ],
                            sleep_seconds=sleep_seconds,
                        )
        else:
            if READY_LABEL in current.labels:
                planned_changes.append(
                    f"#{number}: remove {READY_LABEL} (closed issue)"
                )
                drift_detected = True
                if apply:
                    _run_gh(
                        [
                            "issue",
                            "edit",
                            str(number),
                            "--repo",
                            REPO,
                            "--remove-label",
                            READY_LABEL,
                        ],
                        sleep_seconds=sleep_seconds,
                    )
            if BLOCKED_LABEL in current.labels:
                planned_changes.append(
                    f"#{number}: remove {BLOCKED_LABEL} (closed issue)"
                )
                drift_detected = True
                if apply:
                    _run_gh(
                        [
                            "issue",
                            "edit",
                            str(number),
                            "--repo",
                            REPO,
                            "--remove-label",
                            BLOCKED_LABEL,
                        ],
                        sleep_seconds=sleep_seconds,
                    )

    tracker_state = _read_issue(TRACKER_ISSUE, sleep_seconds=sleep_seconds)
    if TRACK_LABEL not in tracker_state.labels:
        planned_changes.append(f"#{TRACKER_ISSUE}: add {TRACK_LABEL}")
        drift_detected = True
        if apply:
            _run_gh(
                [
                    "issue",
                    "edit",
                    str(TRACKER_ISSUE),
                    "--repo",
                    REPO,
                    "--add-label",
                    TRACK_LABEL,
                ],
                sleep_seconds=sleep_seconds,
            )

    if args.sync_tracker:
        tracker_messages = _sync_tracker_checklist(
            issue_states,
            apply=apply,
            sleep_seconds=sleep_seconds,
        )
        planned_changes.extend(tracker_messages)
        if any("line(s) updated" in message for message in tracker_messages):
            drift_detected = True

    if planned_changes:
        print("\nPlanned changes:")
        for line in planned_changes:
            print(f"- {line}")
    else:
        print("\nNo changes needed; queue governance already aligned.")

    if args.fail_on_drift and drift_detected:
        print("\nDrift detected and --fail-on-drift is set.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
