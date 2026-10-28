"""Tool execution: file marshalling, timeouts, serialization, artifacts.

Request validation lives in :mod:`better_utils.apimodels` (generated Pydantic
models); this module owns what happens *after* the args are valid.
"""

from __future__ import annotations

import asyncio
import io
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import anyio
from PIL import Image

from .schema import ToolSchema

__all__ = ["Artifacts", "RunResult", "ToolError", "marshall_file_args", "run_tool"]

logger = logging.getLogger("better_utils.executor")


class ToolError(Exception):
    """Raise from a tool to abort with a clean, user-facing message."""


@dataclass
class RunResult:
    ok: bool
    type: str = "json"  # "json" | "text" | "image"
    data: Any = None
    image_url: str | None = None
    elapsed_ms: int = 0
    error: str | None = None
    traceback: str | None = None
    status_code: int = 200

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"ok": self.ok, "type": self.type, "data": self.data,
                                "image_url": self.image_url, "elapsed_ms": self.elapsed_ms}
        if self.error is not None:
            body["error"] = self.error
        if self.traceback is not None:
            body["traceback"] = self.traceback
        return body


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------


async def marshall_file_args(schema: ToolSchema, args: dict[str, Any]) -> None:
    """Replace remaining UploadFile markers with raw bytes / PIL images.

    ``File`` args receive the file's bytes; ``ImageFile`` args receive a
    ``PIL.Image.Image``. Raises ToolError for unreadable images.
    """
    for spec in schema.args:
        if spec.type != "file":
            continue
        value = args.get(spec.name)
        if value is None or isinstance(value, bytes):
            continue
        try:
            data = await value.read()
        except Exception as exc:
            raise ToolError(f"could not read uploaded file {spec.name!r}: {exc}") from None
        if not data:
            raise ToolError(f"uploaded file {spec.name!r} is empty")
        if spec.file_shape == "image":
            try:
                args[spec.name] = Image.open(io.BytesIO(data))
            except Exception as exc:
                raise ToolError(
                    f"uploaded file {spec.name!r} is not a valid image ({type(exc).__name__})"
                ) from None
        else:
            args[spec.name] = data


async def run_tool(
    func: Callable,
    args: dict[str, Any],
    *,
    timeout_s: float,
    artifacts: Artifacts,
) -> RunResult:
    """Invoke a tool in a worker thread (or await it) with a hard timeout."""
    started = time.perf_counter()

    try:
        import inspect as _inspect

        if _inspect.iscoroutinefunction(func):
            result = await asyncio.wait_for(func(**args), timeout=timeout_s)
        else:
            result = await asyncio.wait_for(
                anyio.to_thread.run_sync(lambda: func(**args)),
                timeout=timeout_s,
            )
    except asyncio.TimeoutError:
        return _failure(
            f"tool run exceeded the {timeout_s:g}s timeout",
            status_code=504,
            elapsed_ms=_elapsed(started),
            traceback=None,
        )
    except ToolError as exc:
        return _failure(str(exc), status_code=400, elapsed_ms=_elapsed(started), traceback=None)
    except Exception as exc:  # user code blew up
        import traceback as _tb

        return _failure(
            f"{type(exc).__name__}: {exc}",
            status_code=500,
            elapsed_ms=_elapsed(started),
            traceback=_tb.format_exc(),
        )

    return _serialize(result, artifacts=artifacts, started=started)


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _failure(error: str, *, status_code: int, elapsed_ms: int, traceback: str | None) -> RunResult:
    return RunResult(ok=False, error=error, traceback=traceback, elapsed_ms=elapsed_ms, status_code=status_code)


# ---------------------------------------------------------------------------
# serialization
# ---------------------------------------------------------------------------


def _serialize(result: Any, *, artifacts: Artifacts, started: float) -> RunResult:
    try:
        payload: tuple[str, Any, str | None]
        img = _as_image(result)
        if img is not None:
            url = artifacts.save_image(img)
            payload = ("image", None, url)
        elif isinstance(result, str):
            payload = ("text", result, None)
        else:
            payload = ("json", _jsonify(result), None)
        return RunResult(ok=True, type=payload[0], data=payload[1], image_url=payload[2],
                         elapsed_ms=_elapsed(started))
    except Exception as exc:
        import traceback as _tb

        return _failure(
            f"could not serialize tool result ({type(exc).__name__}: {exc})",
            status_code=500,
            elapsed_ms=_elapsed(started),
            traceback=_tb.format_exc(),
        )


def _as_image(result: Any):
    try:
        from PIL import Image

        if isinstance(result, Image.Image):
            return result
    except Exception:  # pragma: no cover - pillow missing
        return None
    return None


def _jsonify(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonify(asdict(value))
    pydantic_dump = getattr(value, "model_dump", None)
    if callable(pydantic_dump):
        try:
            return pydantic_dump(mode="json")
        except TypeError:
            return pydantic_dump()
    if isinstance(value, (set, frozenset, tuple, bytearray)):
        if isinstance(value, bytearray):
            return bytes(value).hex()
        return [_jsonify(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonify(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonify(v) for v in value]
    gen = getattr(value, "__iter__", None)
    if callable(gen):
        return [_jsonify(v) for v in value]
    return str(value)


# ---------------------------------------------------------------------------
# artifacts
# ---------------------------------------------------------------------------


class Artifacts:
    """Stores tool image outputs on disk and exposes them by URL."""

    def __init__(self, directory: Path | str | None = None, *, ttl_s: int = 3600) -> None:
        import tempfile

        if directory is None:
            directory = Path(tempfile.mkdtemp(prefix="better_utils_artifacts_"))
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ttl_s = ttl_s
        logger.debug("artifacts dir: %s", self.dir)

    def save_image(self, image: Any) -> str:
        """Persist an image and return its serving URL."""
        name = f"{uuid.uuid4().hex}.png"
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        path = self.dir / name
        path.write_bytes(buffer.getvalue())
        self._cleanup()
        return f"/api/artifacts/{name}"

    def file_path(self, name: str) -> Path:
        # name is validated upstream: no separators, exact expected suffix
        if "/" in name or "\\" in name or ".." in name:
            raise FileNotFoundError(name)
        path = self.dir / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path

    def _cleanup(self) -> None:
        now = time.time()
        for f in self.dir.iterdir():
            try:
                if now - f.stat().st_mtime > self.ttl_s:
                    f.unlink(missing_ok=True)
            except OSError:  # pragma: no cover
                pass
