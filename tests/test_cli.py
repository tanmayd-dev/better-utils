"""CLI: target resolution, version, banner, and a REAL boot of `bu run`."""

import os
import socket
import subprocess
import sys
import time
import urllib.request

import pytest

from better_utils.cli import main


def test_version(capsys):
    assert main(["--version"]) == 0
    out = capsys.readouterr().out
    assert "bu " in out


def test_run_requires_module_attr_syntax(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "app"])
    assert "module:attribute" in str(excinfo.value)


def test_run_rejects_missing_module(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "does_not_exist_xyz:nope"])
    assert "could not import" in str(excinfo.value)


def test_run_rejects_non_betterutils_target():
    # math.pi exists but is not a BetterUtils app
    with pytest.raises(SystemExit) as excinfo:
        main(["run", "math:pi"])
    assert "not a BetterUtils" in str(excinfo.value)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.mark.slow
def test_full_boot_example_app():
    """End-to-end: subprocess boots `bu run example_app:app`; HTTP works."""
    port = _free_port()
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "better_utils.cli", "run", "example_app:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + 20
    last_err: object = None
    try:
        while time.time() < deadline and proc.poll() is None:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as resp:
                    assert resp.status == 200
                    break
            except Exception as exc:  # not up yet
                last_err = exc
                time.sleep(0.3)
        else:
            pytest.fail(f"server did not come up: last error {last_err}; "
                        f"stdout/err tail: {proc.stdout.read()!r} / {proc.stderr.read()!r}")

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/tools", timeout=5) as resp:
            import json

            body = json.load(resp)
        ids = {t["id"] for t in body["tools"]}
        assert "text.reverse_string" in ids
        assert "bookmarks.add_bookmark" in ids

        run_req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/run/text.reverse_string",
            data=b'{"text": "abc"}',
            headers={"content-type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(run_req, timeout=5) as resp:
            body = json.load(resp)
        assert body["ok"] is True and body["data"] == "cba"

        with urllib.request.urlopen(run_req := urllib.request.Request(
            f"http://127.0.0.1:{port}/api/run/stats.summarize",
            data=b'{"values": [1, 2, 3.5]}',
            headers={"content-type": "application/json"},
            method="POST",
        ), timeout=5) as resp:
            body = json.load(resp)
        assert body["data"]["average"] == 2.1666666666666665

        # settings from env: host/port traveled through the CLI path
        assert body["ok"] is True

        # the banner mentions the dashboard and tools
        proc.terminate()
        out, _ = proc.communicate(timeout=10)
        assert "dashboard" in out and "text.reverse_string" in out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate(timeout=5)
    assert proc.returncode is not None
