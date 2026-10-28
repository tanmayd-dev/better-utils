"""Command line entry point: ``bu run app:app``.

Like uvicorn, the positional argument is ``module:attribute`` resolving to a
:class:`better_utils.BetterUtils` instance.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import os
import sys

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bu",
        description="Better Utils — run a tool server from a BetterUtils app object.",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="serve a BetterUtils app (module:attribute)")
    run.add_argument("target", metavar="APP", help="module:attribute, e.g. app:app")
    run.add_argument("--host", default=None, help="bind address (default: BETTER_UTILS_HOST, 127.0.0.1)")
    run.add_argument("--port", type=int, default=None, help="port (default: BETTER_UTILS_PORT, 8000)")
    run.add_argument("--reload", dest="reload", action="store_true", default=None,
                     help="hot-reload tool files on change (default: BETTER_UTILS_RELOAD)")
    run.add_argument("--no-reload", dest="reload", action="store_false",
                     help="explicitly disable the file watcher")
    run.add_argument("--timeout", type=float, default=None,
                     help="tool execution timeout in seconds (default 60)")
    return parser


def _resolve_target(target: str):
    module_name, sep, attr = target.partition(":")
    if not sep or not attr:
        raise SystemExit(
            f"invalid target {target!r}: expected 'module:attribute', e.g. 'app:app'"
        )
    # Console scripts do not get the caller's cwd on sys.path; uvicorn's CLI
    # does this, and `bu run app:app` is expected to find ./app.py the same way.
    cwd = os.getcwd()
    if cwd not in sys.path:
        sys.path.insert(0, cwd)
    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise SystemExit(f"could not import app module {module_name!r}: {exc}") from exc
    app_obj = getattr(module, attr, None)
    if app_obj is None:
        raise SystemExit(f"module {module_name!r} has no attribute {attr!r}")

    from .app import BetterUtils

    if not isinstance(app_obj, BetterUtils):
        raise SystemExit(
            f"{module_name}:{attr} is not a BetterUtils instance "
            f"(got {type(app_obj).__name__})"
        )
    return app_obj


def _print_banner(app_obj, *, host: str, port: int) -> None:
    tools = app_obj.registry.list_tools()
    errors = app_obj.registry.list_errors()
    width = max((len(t.id) for t in tools), default=10)
    print(f"\nBetter Utils — dashboard: http://{host}:{port}/", flush=True)
    if tools:
        print(f"  {'TOOL'.ljust(width)}  ENDPOINT")
        for t in tools:
            print(f"  {t.id.ljust(width)}  POST /api/run/{t.id}")
    else:
        print("  (no tools registered yet)")
    if errors:
        print("  LOAD ERRORS:")
        for e in errors:
            print(f"    {e.path}: {e.error}")
    print(flush=True)


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.version:
        from . import __version__

        print(f"bu {__version__}")
        return 0

    if args.command != "run":
        _build_parser().print_help()
        return 2

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(name)s: %(message)s")
    app_obj = _resolve_target(args.target)

    overrides: dict[str, object] = {}
    if args.host:
        overrides["host"] = args.host
    if args.port:
        overrides["port"] = args.port
    if args.timeout:
        overrides["timeout_s"] = args.timeout
    if args.reload is not None:
        overrides["reload"] = args.reload
    if overrides:
        app_obj.settings = app_obj.settings.with_overrides(**overrides)

    from .watcher import start_watcher

    asgi_app = app_obj.build()
    if app_obj.settings.reload:
        start_watcher(
            lambda: app_obj.registry,
            on_change=lambda: app_obj.on_registry_changed(),
        )

    _print_banner(app_obj, host=app_obj.settings.host, port=app_obj.settings.port)

    import uvicorn

    try:
        uvicorn.run(
            asgi_app,
            host=app_obj.settings.host,
            port=app_obj.settings.port,
            log_level=app_obj.settings.log_level,
        )
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nbye")
        return 0
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
