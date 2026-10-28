"""Tool test runs — in a pytest *subprocess*, never inside the server.

The old runner executed `pytest.main` in the API process from a GET route:
it poisoned interpreter globals, imported test code into the server, had no
timeout, and mislabeled "no tests collected" as failure. This module runs
``python -m pytest -q`` as a subprocess with a hard timeout and returns a
JSON-ready payload.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

__all__ = ["run_tests_for_tool"]

_TEST_SUFFIXES = ("tests", "test_files")


def find_test_files(tool_path: str | Path) -> list[Path]:
    """Tests live in ``tests/test_<file>.py`` or beside the tool file."""
    p = Path(tool_path)
    if not p.is_absolute():
        p = p.resolve()
    parent = p.parent
    candidates: list[Path] = []
    name = f"test_{p.stem}.py"
    for sub in _TEST_SUFFIXES + ("",):
        candidate = parent / sub / name
        if candidate.is_file() and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def run_tests_for_tool(
    tool_path: str | Path, *, timeout_s: float = 60.0, tools_root: str | Path | None = None
) -> dict:
    """Execute the tests for a tool file; always returns without raising."""
    started = time.perf_counter()
    test_files = find_test_files(tool_path)
    if not test_files:
        return _payload("no_tests", 0, 0, [], "no tests found", started)

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--tb=short",
        "-p", "no:cacheprovider",
        *map(str, test_files),
    ]
    # NOTE: no -q here. The user's own pytest config (e.g. addopts = "-q")
    # already applies in the subprocess, and a second -q would downgrade to
    # -qq, which hides the summary line we parse counts from.
    # `import tools.text` needs the project root; `import text` needs the tools
    # dir itself. Put both on PYTHONPATH so either import style works.
    from better_utils import __file__ as _pkg_file

    p = Path(tool_path).resolve()
    root = _project_root(p)
    pkg_parent = Path(_pkg_file).resolve().parent.parent
    extra_paths = {str(root), str(Path(tools_root) if tools_root else p.parent), str(pkg_parent)}
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env["PYTHONPATH"] = os.pathsep.join([env.get("PYTHONPATH", ""), *sorted(extra_paths)]).lstrip(os.pathsep)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _payload("error", 0, 0, test_files, f"tests timed out after {timeout_s:g}s", started)
    except FileNotFoundError:
        return _payload("error", 0, 0, test_files, "pytest is not installed in this environment", started)

    status, passed, failed = _interpret(proc.returncode, proc.stdout + "\n" + proc.stderr)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "files": [f.name for f in test_files],
        "output": (proc.stdout + proc.stderr).strip()[-4000:],
        "duration_ms": duration_ms,
    }


def _interpret(returncode: int, output: str) -> tuple[str, int, int]:
    if "No module named pytest" in output:
        # runner missing: that is an environment problem, not a test failure
        return "error", 0, 0
    if returncode == 0:
        base = "passed"
    elif returncode == 5:  # pytest: no tests collected
        return "no_tests", 0, 0
    else:
        base = "failed"

    passed = failed = 0
    for m in re.finditer(r"(\d+) (passed|failed)", output):
        if m.group(2) == "passed":
            passed = int(m.group(1))
        else:
            failed = int(m.group(1))
    em = re.search(r"(\d+) error", output)
    if em:
        failed += int(em.group(1))
    # When no summary was parsed we keep 0/0 rather than inventing counts;
    # the status itself still comes from the return code.
    return base, passed, failed


def _payload(status: str, passed: int, failed: int, files, output: str, started: float) -> dict:
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "files": [getattr(f, "name", str(f)) for f in files],
        "output": output,
        "duration_ms": int((time.perf_counter() - started) * 1000),
    }


def _project_root(tool_path: Path) -> Path:
    """Walk up from the tool file until there is no ``tests``-style parent."""
    p = tool_path.parent
    for candidate in [p, *p.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / ".git").exists():
            return candidate
    return p
