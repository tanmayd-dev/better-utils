"""run_tool units: timeouts, async, serialization, artifacts.

Argument validation itself is exercised at the API layer (tests/test_api.py)
against the generated per-tool routes.
"""

import asyncio
from dataclasses import dataclass

from PIL import Image

from better_utils.executor import Artifacts, ToolError, run_tool
from better_utils.schema import parse_tool


def ex_run(func, args, tmp_path, timeout_s=5.0):
    artifacts = Artifacts(directory=tmp_path / "artifacts")
    return asyncio.run(run_tool(func, args, timeout_s=timeout_s, artifacts=artifacts))


def test_run_tool_image_artifact(tmp_path):
    def make(size: int = 10):
        return Image.new("RGB", (size, size), "coral")

    result = ex_run(make, {"size": 10}, tmp_path)
    assert result.ok and result.type == "image"
    assert result.image_url and result.image_url.startswith("/api/artifacts/")
    artifact = tmp_path / "artifacts" / result.image_url.rsplit("/", 1)[-1]
    assert artifact.exists()


def test_run_tool_async_function(tmp_path):
    async def sleepy(seconds: float = 0.05, text: str = "done") -> str:
        await asyncio.sleep(seconds)
        return text

    result = ex_run(sleepy, {"seconds": 0.01}, tmp_path)
    assert result.ok and result.type == "text" and result.data == "done"


def test_run_tool_timeout(tmp_path):
    def never_finish(delay: float = 10):
        import time

        time.sleep(delay)
        return "never"

    result = ex_run(never_finish, {}, tmp_path, timeout_s=0.2)
    assert not result.ok and result.status_code == 504
    assert "timeout" in (result.error or "").lower()


def test_run_tool_toolerror_vs_exception(tmp_path):
    def boom(messy: bool = False):
        if messy:
            raise ValueError("raw failure")
        raise ToolError("clean message")

    clean = ex_run(boom, {"messy": False}, tmp_path)
    assert clean.status_code == 400 and clean.error == "clean message"
    assert clean.traceback is None

    messy = ex_run(boom, {"messy": True}, tmp_path)
    assert messy.status_code == 500
    assert messy.traceback and "raw failure" in messy.error


def test_run_tool_json_serialization(tmp_path):
    @dataclass
    class Row:
        a: int
        b: str

    def produce():
        return {"rows": [Row(1, "x"), Row(2, "y")], "seq": (1, 2), "p": 3.14}

    result = ex_run(produce, {}, tmp_path)
    assert result.ok and result.type == "json"
    assert result.data["rows"] == [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
    assert result.data["seq"] == [1, 2]


def test_run_tool_string_return_hint_via_registry():
    """Return hint decides text vs json at the API layer (see api tests)."""
    def text_out(note: str) -> str:
        return note.upper()

    schema = parse_tool(text_out)
    assert schema.return_hint == "text"

    def dict_out(x: int = 0) -> dict:
        return {"x": x}

    assert parse_tool(dict_out).return_hint == "json"
