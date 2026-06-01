def test_filter_stale_cwd_noise():
    from scripts.capture_recovery_snapshot import filter_stale_cwd_noise

    raw = (
        "shell-init: error retrieving current directory: getcwd: cannot access parent directories: No such file or directory\n"
        "{\n"
        '  "valid": "json"\n'
        "}"
    )
    filtered, detected = filter_stale_cwd_noise(raw)
    assert detected
    assert "shell-init" not in filtered
    assert "valid" in filtered


def test_noninteractive_gh_stale_cwd(monkeypatch):
    import json

    from scripts import noninteractive_gh

    class DummyResult:
        returncode = 0
        stdout = 'shell-init: error retrieving current directory: getcwd: cannot access parent directories\n{"state": "OPEN"}'
        stderr = ""

    def mock_run_gh_throttled(*args, **kwargs):
        return DummyResult()

    monkeypatch.setattr(noninteractive_gh, "run_gh_throttled", mock_run_gh_throttled)
    res = noninteractive_gh.run_gh_json(["issue", "view"])
    assert res == {"state": "OPEN"}
