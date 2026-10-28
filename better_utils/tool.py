"""The ``@tool`` decorator.

Compatible with every usage form::

    @tool                 # bare (the old framework's fatal bug)
    @tool()
    @tool(name="Histogram")

Metadata is attached to the function object itself — no wrapper is ever
returned, so signatures and docstrings stay intact and there is nothing to
get out of sync.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

__all__ = ["is_tool", "mark_tool", "tool"]


def mark_tool(func: Callable, name: str | None = None, group: str | None = None) -> None:
    """Attach registry metadata to a callable."""
    func._is_tool = True  # type: ignore[attr-defined]
    func._tool_name = name  # type: ignore[attr-defined]
    func._tool_group = group  # type: ignore[attr-defined]


def is_tool(obj: Any) -> bool:
    """True when ``obj`` was decorated."""
    return getattr(obj, "_is_tool", False) is True


def tool(func: Callable | None = None, *, name: str | None = None, group: str | None = None):
    """Register a function as a tool.

    Args:
        func: The decorated function (when used bare).
        name: Display title. Defaults to the function name.
        group: Sidebar group. Defaults to the router name, the parent folder,
            or ``"General"``.
    """

    def _attach(f: Callable) -> Callable:
        mark_tool(f, name=name, group=group)
        return f

    if func is None:
        return _attach
    _attach(func)
    return func
