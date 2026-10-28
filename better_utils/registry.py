"""Tool registry: discovery, unique module loading, hot-reload, deletion pruning.

Fixes carried over from the old implementation:
- module identity is path-hashed, so same-stem files in different folders can
  no longer clobber each other in ``sys.modules``;
- tool ids are collision-checked instead of silently overwritten;
- import errors surface in the API (and dashboard) instead of a bare print;
- read access is snapshot-based and writes take a lock, so the watcher thread
  and request handlers cannot race.
"""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import logging
import sys
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schema import ToolSchema, parse_tool
from .tool import is_tool

__all__ = ["DuplicateToolError", "ModuleError", "Tool", "ToolRegistry"]

logger = logging.getLogger("better_utils.registry")


class DuplicateToolError(RuntimeError):
    """Two different sources claim the same tool id."""


@dataclass
class Tool:
    id: str
    func: Callable
    schema: ToolSchema
    group: str
    path: str = ""  # absolute source path; "" for programmatically registered
    display_path: str = ""  # path relative to the discovery root

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "group": self.group,
            **self.schema.to_dict(),
        }


@dataclass
class ModuleError:
    path: str
    error: str
    traceback: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "error": self.error, "traceback": self.traceback}


def _module_digest(path: Path) -> str:
    return hashlib.sha1(str(path).encode()).hexdigest()[:12]


class ToolRegistry:
    """Holds every registered tool and the load errors of its modules."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._tools: dict[str, Tool] = {}          # id -> Tool
        self._ids_by_path: dict[str, list[str]] = {}  # absolute path -> ids
        self._errors: dict[str, ModuleError] = {}  # absolute path -> error
        self.watch_roots: set[Path] = set()

    # ------------------------------------------------------------------
    # read access (snapshot semantics)
    # ------------------------------------------------------------------

    def list_tools(self) -> list[Tool]:
        with self._lock:
            return sorted(self._tools.values(), key=lambda t: (t.group, t.schema.name, t.id))

    def get_tool(self, tool_id: str) -> Tool | None:
        with self._lock:
            return self._tools.get(tool_id)

    def list_errors(self) -> list[ModuleError]:
        with self._lock:
            return sorted(self._errors.values(), key=lambda e: e.path)

    def reset(self) -> None:
        """Drop every tool and error; keep watch roots (hot-reload safe)."""
        with self._lock:
            self._tools.clear()
            self._ids_by_path.clear()
            self._errors.clear()

    # ------------------------------------------------------------------
    # registration
    # ------------------------------------------------------------------

    def register_callable(
        self,
        func: Callable,
        *,
        tool_id: str,
        group: str,
    ) -> Tool:
        """Register a decorated function directly (``app.tool``, routers)."""
        if not is_tool(func):
            raise ValueError(f"{func!r} is not marked as a tool")
        schema = parse_tool(func)
        return self._register(
            func=func,
            schema=schema,
            tool_id=tool_id,
            group=group,
            path="",
            display_path="app",
        )

    def _register(
        self,
        *,
        func: Callable,
        schema: ToolSchema,
        tool_id: str,
        group: str,
        path: str,
        display_path: str,
    ) -> Tool:
        with self._lock:
            existing = self._tools.get(tool_id)
            if existing is not None:
                same_file = existing.path == path
                same_function = existing.func is func
                if not same_file and existing.path:
                    raise DuplicateToolError(
                        f"tool id {tool_id!r} is already registered from "
                        f"{existing.display_path!r}; supply a distinct prefix"
                    )
                if not existing.path and not same_function:
                    raise DuplicateToolError(
                        f"tool id {tool_id!r} is already in use by a different function"
                    )
            tool = Tool(
                id=tool_id,
                func=func,
                schema=schema,
                group=group,
                path=path,
                display_path=display_path,
            )
            self._tools[tool_id] = tool
            if path:
                ids = self._ids_by_path.setdefault(path, [])
                if tool_id not in ids:
                    ids.append(tool_id)
        logger.debug("registered tool %s (%s)", tool_id, display_path or "app")
        return tool

    # ------------------------------------------------------------------
    # filesystem / module discovery
    # ------------------------------------------------------------------

    def load_dir(self, tools_dir: str | Path, *, create: bool = False) -> int:
        """Scan a directory tree for tools; returns the number registered."""
        root = _resolve_dir(tools_dir)
        if root.exists():
            if not root.is_dir():
                raise NotADirectoryError(f"{root} is not a directory")
        elif create:
            root.mkdir(parents=True, exist_ok=True)
        else:
            logger.warning("tools directory %s does not exist yet; skipping scan", root)
            return 0
        self.watch_roots.add(root)
        logger.info("scanning for tools in %s", root)
        importlib.invalidate_caches()

        count = 0
        for py in sorted(root.rglob("*.py")):
            if self._skip_file(py, root):
                continue
            count += self._load_file(py, root)
        logger.info("registered %d tools from %s", count, root)
        return count

    def load_module_name(self, module_name: str) -> int:
        """Discover tools in an importable module (installed package)."""
        importlib.invalidate_caches()
        module = importlib.import_module(module_name)
        file = getattr(module, "__file__", None)
        root = Path(file).parent if file else Path.cwd()
        return self._register_module_tools(module, module_name, Path(file) if file else None, root)

    def load_file(self, py_path: str | Path) -> int:
        """Discover tools in one explicit ``.py`` file."""
        p = Path(py_path).resolve()
        if not p.is_file():
            logger.warning("tool file %s does not exist", p)
            return 0
        root = self._watch_root_for(p) or p.parent
        self.watch_roots.add(root)
        return 0 if self._skip_file(p, root) else self._load_file(p, root)

    def reload_path(self, path: str | Path) -> None:
        """Reload one file: prune its tools first, then re-import."""
        p = Path(path).resolve()
        if not self._under_watch(p):
            return
        root = self._watch_root_for(p) or p.parent
        self._prune_path(p)
        if p.exists() and not self._skip_file(p, root):
            self._load_file(p, root)

    def remove_path(self, path: str | Path) -> None:
        """Drop every tool that was loaded from ``path`` (file deleted/moved)."""
        p = Path(path).resolve()
        if not self._under_watch(p):
            return
        self._prune_path(p)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    @staticmethod
    def _skip_file(py: Path, root: Path) -> bool:
        if py.name.startswith("__") or py.name == "conftest.py":
            return True
        try:
            rel = py.relative_to(root)
        except ValueError:
            return False
        return any(part in ("tests", "test_files") or part.startswith((".", "__")) for part in rel.parts[:-1])

    def tools_root_for(self, path: str | Path) -> Path:
        """The discovery root that contains ``path`` (for subprocess envs)."""
        p = Path(path).resolve()
        with self._lock:
            for root in self.watch_roots:
                if p.is_relative_to(root):
                    return root
        return p.parent

    def _under_watch(self, p: Path) -> bool:
        with self._lock:
            return any(p.is_relative_to(root) for root in self.watch_roots)

    def _watch_root_for(self, p: Path) -> Path | None:
        with self._lock:
            for root in sorted(self.watch_roots, key=lambda _r: -len(str(_r))):
                if p.is_relative_to(root):
                    return root
        return None

    def _prune_path(self, p: Path) -> None:
        key = str(p)
        with self._lock:
            for tid in self._ids_by_path.pop(key, []):
                self._tools.pop(tid, None)
            self._errors.pop(key, None)
        logger.info("pruned %s", key)

    def _load_file(self, py: Path, root: Path) -> int:
        module_name = f"better_utils_tools_{_module_digest(py)}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, str(py))
            if spec is None or spec.loader is None:
                raise ImportError(f"cannot create import spec for {py}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
        except Exception:
            self._record_error(py, root)
            logger.error("failed to load module %s", py)
            return 0
        with self._lock:
            self._errors.pop(str(py), None)
        return self._register_module_tools(module, module_name, py, root)

    def _record_error(self, py: Path, root: Path) -> None:
        try:
            display = str(py.relative_to(root))
        except ValueError:
            display = str(py)
        tb = traceback.format_exc()
        lines = tb.strip().splitlines()
        msg = lines[-1] if lines else "import failed"
        with self._lock:
            self._errors[str(py)] = ModuleError(path=display, error=msg, traceback=tb)

    def _register_module_tools(
        self, module: object, module_name: str, source: Path | None, root: Path
    ) -> int:
        rel = source.relative_to(root) if source and source.is_relative_to(root) else None
        if rel is not None:
            dotted = ".".join(rel.with_suffix("").parts)
            if len(rel.parts) > 1:
                folder_group = rel.parts[0].capitalize()
            else:
                folder_group = rel.stem.capitalize() if rel.stem else "General"
            display = str(rel)
        else:
            dotted = module_name
            folder_group = "General"
            display = module_name

        count = 0
        for attr in vars(module).values():
            if not callable(attr) or not is_tool(attr):
                continue
            if getattr(attr, "__module__", None) != module_name:
                continue  # re-exported tool from another module: skip here
            explicit_group = getattr(attr, "_tool_group", None)
            tool_id = f"{dotted}.{attr.__name__}"
            try:
                self._register(
                    func=attr,
                    schema=parse_tool(attr),
                    tool_id=tool_id,
                    group=explicit_group or folder_group,
                    path=str(source) if source else "",
                    display_path=display,
                )
                count += 1
            except DuplicateToolError as exc:
                logger.error("%s (%s)", exc, display)
        return count


def _resolve_dir(tools_dir: str | Path) -> Path:
    return Path(tools_dir).expanduser().resolve()
