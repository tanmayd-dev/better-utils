"""Model of a group of tools that are included together, FastAPI-router style."""

from __future__ import annotations

from collections.abc import Callable

from .tool import mark_tool

__all__ = ["Router"]

_SLUG_SAFE = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-.")


def slugify(text: str) -> str:
    return "".join(c.lower() if c in _SLUG_SAFE else "-" for c in text)


class Router:
    """Collects tools so they can be registered in one call::

        text = Router("text")

        @text.tool
        def reverse_string(s: str) -> str:
            ...

        app.include_router(text)
    """

    def __init__(self, name: str, *, group: str | None = None):
        """``name`` doubles as the default id prefix and sidebar group."""
        if not name or not isinstance(name, str):
            raise ValueError("Router name must be a non-empty string")
        self.name = name
        self.group = group
        self._tools: list[Callable] = []

    def tool(self, func: Callable | None = None, *, name: str | None = None, group: str | None = None):
        """Same contract as :func:`better_utils.tool` but scoped to this router."""

        def _attach(f: Callable) -> Callable:
            mark_tool(f, name=name, group=group)
            self._tools.append(f)
            return f

        if func is None:
            return _attach
        _attach(func)
        return func

    @property
    def tools(self) -> list[Callable]:
        return list(self._tools)
