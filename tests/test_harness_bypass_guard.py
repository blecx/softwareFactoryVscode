import os
import subprocess
import sys


def test_bypass_guard_rejects_missing_token():
    # Attempt to run the bypass guard without HARNESS_BYPASS_ACK
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "harness_bypass_guard.py"
    )

    env = os.environ.copy()
    if "HARNESS_BYPASS_ACK" in env:
        del env["HARNESS_BYPASS_ACK"]

    result = subprocess.run(
        [sys.executable, script_path, "--reason", "Test reason"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Explicit human authorization missing or incorrect" in result.stderr
    assert "Bypass rejected" in result.stderr


def test_bypass_guard_rejects_incorrect_token():
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "harness_bypass_guard.py"
    )

    env = os.environ.copy()
    env["HARNESS_BYPASS_ACK"] = "WRONG_TOKEN"

    result = subprocess.run(
        [sys.executable, script_path, "--reason", "Test reason"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Explicit human authorization missing or incorrect" in result.stderr


def test_bypass_guard_accepts_correct_token(tmp_path):
    script_path = os.path.join(
        os.path.dirname(__file__), "..", "scripts", "harness_bypass_guard.py"
    )

    env = os.environ.copy()
    env["HARNESS_BYPASS_ACK"] = "I_AUTHORIZE_BYPASS"

    # Run in a temporary directory so we don't write generic logs to the real .tmp if we don't want to,
    # but the script uses .tmp relative to cwd.
    result = subprocess.run(
        [sys.executable, script_path, "--reason", "Valid test reason"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Bypass explicitly authorized" in result.stdout
    assert "Audit log appended" in result.stdout

    log_file = tmp_path / ".tmp" / "emergency-bypass.log"
    assert log_file.exists()
    content = log_file.read_text()
    assert "BYPASS REASON: Valid test reason" in content
