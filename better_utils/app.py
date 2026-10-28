"""The ``BetterUtils`` application object.

FastAPI-style interface::

    # app.py
    from better_utils import BetterUtils, Router
    from routers import text

    app = BetterUtils(title="My Utils")
    app.include_router(text)
    # optional: app.discover("tools")
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError as PydValidationError

from .apimodels import (
    RunErrorBody,
    RunResponse,
    TestResponse,
    ValidationErrorBody,
    build_request_model,
    items_from_request_errors,
    make_json_endpoint,
    make_multipart_endpoint,
    validation_response,
)
from .config import Settings, resolve_static_dir
from .executor import (
    Artifacts,
    RunResult,
    ToolError,
    marshall_file_args,
    run_tool,
)
from .registry import ToolRegistry
from .router import Router, slugify
from .tool import tool as _tool

__all__ = ["BetterUtils"]

logger = logging.getLogger("better_utils.app")


class BetterUtils:
    """Holds tools, builds the FastAPI app, owns runtime settings."""

    def __init__(self, *, title: str = "Better Utils", tools_dir: str | Path | None = None):
        self.settings: Settings = Settings.from_env()
        self.registry = ToolRegistry()
        self.artifacts = Artifacts()
        self.title = title
        self._built: FastAPI | None = None
        self._route_tools: dict[str, Any] = {}  # tool_id -> Tool behind each run route
        # registration journal, replayed when the registry is rebuilt
        self._discoveries: list[str] = []
        self._root_tools: list[tuple[Callable, str | None, str | None]] = []
        self._router_includes: list[tuple[Router, str, str]] = []

        env_tools = self.settings.tools_dir
        if tools_dir is not None:
            self.discover(tools_dir)
        elif env_tools is not None:
            self.discover(env_tools)

    # ------------------------------------------------------------------
    # registration API
    # ------------------------------------------------------------------

    def tool(self, func: Callable | None = None, *, name: str | None = None, group: str | None = None):
        """Register a tool at the root level (id = function name, group "General")."""

        def _register(f: Callable) -> Callable:
            _tool(f, name=name, group=group)
            self.registry.register_callable(f, tool_id=f.__name__, group=group or "General")
            self._root_tools.append((f, name, group))
            return f

        if func is None:
            return _register
        return _register(func)

    def include_router(self, router: Router, *, prefix: str | None = None) -> None:
        """Include every tool collected by ``router``.

        The default id prefix is the router's own name; override with
        ``prefix=`` (``""`` disables prefixing entirely).
        """
        resolved = slugify(prefix if prefix is not None else router.name)
        group = router.group or (resolved.capitalize() if resolved else "General")
        for func in router.tools:
            _tool(func)
            tool_id = f"{resolved}.{func.__name__}" if resolved else func.__name__
            self.registry.register_callable(func, tool_id=tool_id, group=group)
        self._router_includes.append((router, resolved, group))
        self._routers_note(router, resolved)

    def _routers_note(self, router: Router, resolved: str) -> None:
        logger.info(
            "router %s included: %s%s",
            router.name,
            resolved + "." if resolved else "",
            ", ".join(f.__name__ for f in router.tools),
        )

    def discover(self, target: str | Path) -> None:
        """Scan a directory (or an importable module/package) for ``@tool`` functions."""
        entry = str(target)
        if entry not in self._discoveries:
            self._discoveries.append(entry)
        self.reload_one(entry)

    def reload_one(self, target: str | Path) -> int:
        p = Path(target)
        if p.is_file() and p.suffix == ".py":
            return self.registry.load_file(p)
        if p.is_dir() or self._looks_like_dir(str(target)):
            return self.registry.load_dir(p)
        return self.registry.load_module_name(str(target))

    @staticmethod
    def _looks_like_dir(name: str) -> bool:
        return "/" in name or str(name) == "." or name.startswith("./")

    # ------------------------------------------------------------------
    # rebuild / scan
    # ------------------------------------------------------------------

    def rescan(self) -> None:
        """Rebuild the registry in-place from the journal (dirs, root tools, routers)."""
        # reset() keeps object identity so hot-reload callbacks and route
        # closures continue to observe the same registry
        self.registry.reset()
        for entry in self._discoveries:
            self.reload_one(entry)
        for func, name, group in self._root_tools:
            _tool(func, name=name, group=group)
            self.registry.register_callable(func, tool_id=func.__name__, group=group or "General")
        for router, resolved, group in self._router_includes:
            for func in router.tools:
                _tool(func)
                tool_id = f"{resolved}.{func.__name__}" if resolved else func.__name__
                self.registry.register_callable(func, tool_id=tool_id, group=group)

    # ------------------------------------------------------------------
    # app construction
    # ------------------------------------------------------------------

    def build(self, *, force_rescan: bool = False) -> FastAPI:
        """Create the FastAPI app: routes, static dashboard, CORS."""
        fa = FastAPI(title=self.title)
        self._built = fa

        if force_rescan:
            self.rescan()
        self._routes(fa)

        static_dir = resolve_static_dir(self.settings.static_dir)
        if static_dir is not None:
            fa.mount("/", StaticFiles(directory=str(static_dir), html=True), name="dashboard")
            logger.info("dashboard mounted from %s", static_dir)
        else:
            logger.warning(
                "no dashboard bundle at %s (API-only mode); build it with "
                "scripts/build_ui.sh or set BETTER_UTILS_STATIC_DIR",
                self.settings.static_dir,
            )
        return fa

    # ------------------------------------------------------------------
    # per-tool run routes (documented API)
    # ------------------------------------------------------------------

    def _build_run_route(self, tool) -> APIRoute:
        schema = tool.schema
        prose = [p for p in (schema.description, schema.long_description) if p]
        endpoint = (
            make_multipart_endpoint(tool, self._execute_tool_request)
            if _accepts_files(schema)
            else make_json_endpoint(tool, self._execute_tool_request)
        )
        return APIRoute(
            f"/api/run/{tool.id}",
            endpoint,
            methods=["POST"],
            name=f"run_{tool.id}",
            summary=schema.name or tool.id,
            description="\n\n".join(prose) or None,
            response_model=RunResponse,
            tags=[tool.group] if tool.group else None,
            responses={
                400: {"model": RunErrorBody, "description": "Tool raised ToolError"},
                422: {"model": ValidationErrorBody, "description": "Validation failed"},
                500: {"model": RunErrorBody, "description": "Tool crashed"},
                504: {"model": RunErrorBody, "description": "Tool timed out"},
            },
        )

    def _sync_run_routes(self, fa: FastAPI) -> None:
        """Reconcile per-tool run routes with the current registry.

        Routes for changed/vanished tools are dropped; new/changed ones are
        inserted *before* the catch-all (Starlette is first-match-wins) and
        the cached OpenAPI schema is invalidated.
        """
        routes = fa.router.routes
        prefix = "/api/run/"
        catchall_path = prefix + "{tool_id}"

        tools = {t.id: t for t in self.registry.list_tools()}
        for route in list(routes):
            path = getattr(route, "path", None)
            if not path or not path.startswith(prefix) or path == catchall_path:
                continue
            tid = path[len(prefix):]
            if tools.get(tid) is not self._route_tools.get(tid):
                routes.remove(route)
                self._route_tools.pop(tid, None)

        insert_at = next(
            (i for i, r in enumerate(routes) if getattr(r, "path", None) == catchall_path),
            len(routes),
        )
        for tid, tool in tools.items():
            if tid in self._route_tools:
                continue
            routes.insert(insert_at, self._build_run_route(tool))
            self._route_tools[tid] = tool
            insert_at += 1
        fa.openapi_schema = None  # /openapi.json regenerates on next request

    def on_registry_changed(self) -> None:
        """Hot-reload hook: refresh run routes + invalidate the docs cache."""
        if self._built is not None:
            self._sync_run_routes(self._built)

    # ------------------------------------------------------------------
    # shared run pipeline
    # ------------------------------------------------------------------

    async def _execute_tool_request(self, tool, args: dict[str, Any]):
        """File checks/marshalling, execution, and the response envelope."""
        schema = tool.schema
        for spec in schema.args:
            if spec.type != "file":
                continue
            value = args.get(spec.name)
            content_type = getattr(value, "content_type", None)
            if (
                value is not None
                and spec.accept
                and "image" in spec.accept
                and content_type
                and not content_type.startswith("image/")
            ):
                return validation_response(
                    [{"name": spec.name, "msg": f"an image file is required, got {content_type!r}"}]
                )
        try:
            await marshall_file_args(schema, args)
        except ToolError as exc:
            return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})
        except Exception as exc:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": f"file handling failed: {exc}"},
            )
        result: RunResult = await run_tool(
            tool.func, args, timeout_s=self.settings.timeout_s, artifacts=self.artifacts
        )
        if not result.ok:
            return JSONResponse(status_code=result.status_code, content=result.to_dict())
        return result.to_dict()

    # ------------------------------------------------------------------
    # route table
    # ------------------------------------------------------------------

    def _routes(self, fa: FastAPI) -> None:
        registry = self.registry

        @fa.get("/health", summary="Liveness", tags=["Meta"])
        def health() -> dict[str, Any]:
            return {"status": "ok", "tools": len(registry.list_tools())}

        @fa.get(
            "/api/tools",
            summary="Machine-readable tool catalog",
            description="Argument specs for every tool; the dashboard builds its "
            "forms from this. Per-tool documented routes live at POST /api/run/{tool_id}.",
            tags=["Meta"],
        )
        def tools_list():
            return {
                "tools": [t.to_dict() for t in registry.list_tools()],
                "errors": [e.to_dict() for e in registry.list_errors()],
            }

        @fa.post(
            "/api/test/{tool_id}",
            name="test_tool",
            summary="Run a tool's tests",
            description="Runs the tool module's pytest suite in a subprocess.",
            response_model=TestResponse,
            tags=["Meta"],
            responses={404: {"model": RunErrorBody, "description": "Unknown tool"}},
        )
        def test_tool_endpoint(tool_id: str):
            from .tester import run_tests_for_tool

            found = registry.get_tool(tool_id)
            if found is None:
                raise HTTPException(status_code=404, detail=f"tool {tool_id!r} not found")
            return run_tests_for_tool(
                found.path,
                timeout_s=self.settings.test_timeout_s,
                tools_root=registry.tools_root_for(found.path) if found.path else None,
            )

        @fa.get("/api/artifacts/{name}", summary="Fetch an image artifact", tags=["Meta"])
        def artifact_endpoint(name: str):
            try:
                path = self.artifacts.file_path(name)
            except FileNotFoundError:
                raise HTTPException(status_code=404, detail="artifact not found") from None
            return Response(content=path.read_bytes(), media_type="image/png")

        # Catch-all, hidden from the docs: nice 404 for unknown ids, and the
        # run pipeline for tools registered *after* build() (no per-tool
        # route exists yet — programmatic late registration).
        @fa.post("/api/run/{tool_id}", name="run_fallback", include_in_schema=False)
        async def run_fallback(tool_id: str, request: Request):
            found = registry.get_tool(tool_id)
            if found is None:
                raise HTTPException(status_code=404, detail=f"tool {tool_id!r} not found")
            schema = found.schema
            if _accepts_files(schema):
                form = await request.form()
                known = {a.name for a in schema.args}
                raw: dict[str, Any] = {}
                for key, value in form.multi_items():
                    if _is_upload(value):
                        raw.setdefault(key, value)
                    else:
                        raw[key] = value
                endpoint = make_multipart_endpoint(found, self._execute_tool_request)
                return await endpoint(**{k: v for k, v in raw.items() if k in known})
            try:
                body_json = await request.json()
            except Exception:
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "error": "request body must be a JSON object"},
                )
            if not isinstance(body_json, dict):
                return JSONResponse(
                    status_code=400,
                    content={"ok": False, "error": "request body must be a JSON object"},
                )
            model = build_request_model(found)
            if model is not None:
                try:
                    args = model.model_validate(body_json).model_dump()
                except PydValidationError as exc:
                    return validation_response(items_from_request_errors(exc.errors()))
            else:
                args = {}
            return await self._execute_tool_request(found, args)

        # Per-tool documented routes go right before the catch-all.
        self._sync_run_routes(fa)

        # Keep FastAPI's 422s in the frozen contract shape.
        @fa.exception_handler(RequestValidationError)
        async def validation_contract(request: Request, exc: RequestValidationError):
            return validation_response(items_from_request_errors(exc.errors()))

        origins = self.settings.cors_origins
        if origins:
            from fastapi.middleware.cors import CORSMiddleware

            fa.add_middleware(
                CORSMiddleware,
                allow_origins=origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )


def _is_upload(value: Any) -> bool:
    return hasattr(value, "filename") and hasattr(value, "read")


def _accepts_files(schema) -> bool:
    return any(a.type == "file" for a in schema.args)
