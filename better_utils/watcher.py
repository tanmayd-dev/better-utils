"""File watching with debounce, create/rename/delete handling.

Reliability notes (all of these failed in the old backend):
- editors that save via temp-file + rename emit ``moved`` events, not
  ``modified``: both are handled;
- deleted files *prune* their tools instead of registering zombies forever;
- concurrent events for one save collapse into a single reload (debounce);
- handler exceptions are logged and can never kill the observer thread.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.events import (
    FileSystemEvent,
    FileSystemEventHandler,
    FileSystemMovedEvent,
)
from watchdog.observers import Observer

logger = logging.getLogger("better_utils.watcher")

__all__ = ["start_watcher"]

_DEBOUNCE_S = 0.3


class _DebouncedHandler(FileSystemEventHandler):
    """Reacts to .py changes under the registry's watch roots."""

    def __init__(self, get_registry, on_change=None) -> None:  # lambda: app.registry
        super().__init__()
        self._get_registry = get_registry
        self._on_change = on_change
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()
        self._actions: dict[str, str] = {}  # path -> "reload" | "remove"

    def dispatch(self, event: FileSystemEvent) -> None:  # type: ignore[override]
        # exceptions must never propagate to the watchdog thread
        try:
            super().dispatch(event)
        except Exception:
            logger.exception("watcher handler failed")

    # event kinds --------------------------------------------------------
    def on_modified(self, event: FileSystemEvent) -> None:
        self._enqueue(event.src_path, "reload")

    def on_created(self, event: FileSystemEvent) -> None:
        self._enqueue(event.src_path, "reload")

    def on_moved(self, event: FileSystemMovedEvent) -> None:
        self._enqueue(event.src_path, "remove")
        self._enqueue(event.dest_path, "reload")

    def on_deleted(self, event: FileSystemEvent) -> None:
        self._enqueue(event.src_path, "remove")

    # internals ------------------------------------------------------------
    def _enqueue(self, raw_path: bytes | str, action: str) -> None:
        try:
            path = raw_path.decode() if isinstance(raw_path, bytes) else str(raw_path)
        except UnicodeDecodeError:
            return
        if not path.endswith(".py"):
            return
        registry = self._get_registry()
        if registry is None:
            return
        resolved = Path(path).resolve()
        if not any(resolved.is_relative_to(root) for root in list(registry.watch_roots)):
            return
        if registry._skip_file(resolved, resolved.parent):
            return

        with self._lock:
            self._actions[resolved] = (
                "reload" if action == "reload" else self._actions.get(resolved, "remove")
            )
            pending = self._timers.get(resolved)
            if pending is not None:
                pending.cancel()
            timer = threading.Timer(_DEBOUNCE_S, self._fire, args=(resolved,))
            timer.daemon = True
            self._timers[resolved] = timer
            timer.start()

    def _fire(self, resolved: Path) -> None:
        with self._lock:
            self._timers.pop(resolved, None)
            action = self._actions.pop(str(resolved), "reload")
        registry = self._get_registry()
        if registry is None:
            return
        try:
            if action == "remove":
                registry.remove_path(str(resolved))
            else:
                registry.reload_path(str(resolved))
        except Exception:
            logger.exception("hot-reload failed for %s", resolved)
        finally:
            # route table + OpenAPI cache must track the registry either way
            if self._on_change is not None:
                try:
                    self._on_change()
                except Exception:
                    logger.exception("hot-reload on_change callback failed")


def start_watcher(get_registry, on_change=None) -> Observer | None:
    """Start a daemon observer over every watch root known to the registry.

    ``get_registry`` is a zero-arg callable returning the *current* registry
    (rescan keeps object identity, but passing the accessor is safer than a
    captured instance). ``on_change`` is a zero-arg callback fired after each
    reload/remove (the app uses it to re-sync its per-tool routes).
    """
    registry = get_registry()
    observed = sorted(registry.watch_roots)
    if not observed:
        logger.info("no watch roots; watcher not started")
        return None

    handler = _DebouncedHandler(get_registry, on_change)
    observer = Observer()
    observer.daemon = True
    for root in observed:
        observer.schedule(handler, str(root), recursive=True)
    observer.start()
    logger.info("watching %s and %d more directory(ies)", observed[0], max(0, len(observed) - 1))
    return observer
