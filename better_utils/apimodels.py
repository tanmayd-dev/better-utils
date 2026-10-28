"""Generated Pydantic models + endpoint factories for the documented API.

Each JSON tool gets its own request model (built from its :class:`ArgSpec`
list) so ``/openapi.json`` documents the exact arguments and Pydantic becomes
the validator. File tools get a dynamic multipart signature (``UploadFile`` /
``Form`` parameters). Response envelopes are declared here too.

This module deliberately does NOT use postponed annotations: endpoint
annotations must evaluate eagerly for FastAPI to introspect them.
"""

import inspect
from typing import TYPE_CHECKING, Annotated, Any, Literal

from fastapi import File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    create_model,
)
from pydantic import ValidationError as PydValidationError

from .schema import ArgSpec, ToolSchema

if TYPE_CHECKING:
    from .registry import Tool

__all__ = [
    "RunErrorBody",
    "RunResponse",
    "TestResponse",
    "ValidationErrorBody",
    "ValidationItem",
    "build_multipart_params",
    "build_request_model",
    "items_from_adapter_error",
    "items_from_request_errors",
    "make_json_endpoint",
    "make_multipart_endpoint",
    "validation_response",
]

# ---------------------------------------------------------------------------
# response envelopes
# ---------------------------------------------------------------------------


class RunResponse(BaseModel):
    """Run envelope: success payload or tool-failure details."""

    ok: bool
    type: Literal["json", "text", "image"]
    data: Any = None
    image_url: str | None = None
    elapsed_ms: int
    error: str | None = None
    traceback: str | None = None


class RunErrorBody(BaseModel):
    """Non-2xx error body for run endpoints (400/500/504)."""

    ok: bool = False
    error: str
    traceback: str | None = None


class ValidationItem(BaseModel):
    name: str
    msg: str


class ValidationErrorBody(BaseModel):
    """422 body: which arguments failed and why."""

    ok: bool = False
    error: str
    validation: list[ValidationItem]


class TestResponse(BaseModel):
    """Result of running a tool module's pytest suite."""

    status: Literal["passed", "failed", "no_tests", "error"]
    passed: int
    failed: int
    files: list[str]
    output: str
    duration_ms: int


# ---------------------------------------------------------------------------
# annotation mapping (ArgSpec -> pydantic)
# ---------------------------------------------------------------------------

_SCALAR_ANN: dict[str, Any] = {"string": str, "boolean": bool}
_ITEM_ANN: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool}
_FORM_JSON_TYPES = ("list", "dict")  # multipart: arrive as JSON text in a form field


def _no_bool(value: Any) -> Any:
    # parity with the old validator: booleans are not integers/numbers.
    # ValueError (not TypeError) because pydantic turns it into a 422.
    if isinstance(value, bool):
        raise ValueError("booleans are not numbers")  # noqa: TRY004
    return value


def _enum_coercer(choices: list):
    def _coerce(value: Any) -> Any:
        if isinstance(value, str):
            for choice in choices:
                if value == str(choice):
                    return choice  # native type, not the string form
        return value

    return _coerce


def _annotation(spec: ArgSpec) -> Any:
    """Pydantic annotation for one arg (JSON body or typed adapter)."""
    t = spec.type
    if t == "enum":
        choices = spec.choices or []
        if choices:
            ann: Any = Annotated[
                Literal.__getitem__(tuple(choices)),
                BeforeValidator(_enum_coercer(choices)),
            ]
        else:
            ann = str
    elif t == "integer":
        ann = Annotated[int, BeforeValidator(_no_bool)]
    elif t == "number":
        ann = Annotated[float, BeforeValidator(_no_bool)]
    elif t in _SCALAR_ANN:
        ann = _SCALAR_ANN[t]
    elif t == "list":
        inner = _ITEM_ANN.get(spec.items_type or "", Any)
        if spec.items_type in ("integer", "number"):
            ann = list[Annotated[inner, BeforeValidator(_no_bool)]]
        else:
            ann = list[inner]
    elif t == "dict":
        ann = dict
    else:
        ann = Any
    if spec.nullable:
        ann = ann | None
    return ann


def _field_kwargs(spec: ArgSpec) -> dict[str, Any]:
    """Field constraints for a JSON body field (only what the type supports)."""
    kwargs: dict[str, Any] = {}
    if spec.description:
        kwargs["description"] = spec.description
    if spec.type in ("integer", "number"):
        if spec.min is not None:
            kwargs["ge"] = spec.min
        if spec.max is not None:
            kwargs["le"] = spec.max
    elif spec.type == "string":
        if spec.min_length is not None:
            kwargs["min_length"] = spec.min_length
        if spec.max_length is not None:
            kwargs["max_length"] = spec.max_length
    return kwargs


# ---------------------------------------------------------------------------
# error shaping (frozen contract: {ok, error, validation: [{name, msg}]})
# ---------------------------------------------------------------------------


def validation_response(errors: list[dict[str, str]]) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"ok": False, "error": "Validation failed", "validation": errors},
    )


def items_from_adapter_error(name: str, exc: PydValidationError) -> list[dict[str, str]]:
    """One arg's TypeAdapter errors -> contract items ("item 1: ..." prefix)."""
    items: list[dict[str, str]] = []
    for err in exc.errors():
        msg = err.get("msg", "invalid value")
        loc = err.get("loc", ())
        if loc and isinstance(loc[0], int):
            msg = f"item {loc[0]}: {msg}"
        items.append({"name": name, "msg": msg})
    return items


def items_from_request_errors(errors: list[dict]) -> list[dict[str, str]]:
    """FastAPI/pydantic error list -> contract items (dotted loc names)."""
    items: list[dict[str, str]] = []
    for err in errors:
        loc = [str(p) for p in err.get("loc", ()) if p != "body"]
        items.append({"name": ".".join(loc) or "body", "msg": err.get("msg", "invalid value")})
    return items


# ---------------------------------------------------------------------------
# JSON tools: request model + endpoint
# ---------------------------------------------------------------------------


def build_request_model(tool: "Tool") -> type[BaseModel] | None:
    """Pydantic body model for a JSON tool; None for file tools / no args."""
    schema: ToolSchema = tool.schema
    if any(a.type == "file" for a in schema.args):
        return None
    fields: dict[str, Any] = {}
    for spec in schema.args:
        ann = _annotation(spec)
        kwargs = _field_kwargs(spec)
        if spec.required:
            fields[spec.name] = (ann, Field(..., **kwargs))
        else:
            fields[spec.name] = (ann, Field(spec.default, **kwargs))
    if not fields:
        return None
    name = "RunArgs_" + tool.id.replace(".", "_").replace("-", "_")
    return create_model(name, __config__=ConfigDict(extra="forbid"), **fields)


def make_json_endpoint(tool: "Tool", execute) -> Any:
    """Endpoint ``(payload) -> response`` for a JSON tool.

    ``execute(tool, args)`` is the app's shared run pipeline.
    """
    model = build_request_model(tool)
    if model is not None:

        async def endpoint(payload: model):  # type: ignore[valid-type]
            return await execute(tool, payload.model_dump())

    else:

        async def endpoint():
            return await execute(tool, {})

    endpoint.__name__ = "run_" + tool.id.replace(".", "_")
    return endpoint


# ---------------------------------------------------------------------------
# file tools: multipart signature + endpoint
# ---------------------------------------------------------------------------


def build_multipart_params(tool: "Tool") -> list[inspect.Parameter]:
    """FastAPI parameters for a file tool's multipart route.

    Files -> ``UploadFile``; scalars -> typed ``Form`` fields; list/dict args
    -> JSON-text form fields parsed in the endpoint; enums -> string form
    fields with the choices surfaced via ``json_schema_extra``.
    """
    params: list[inspect.Parameter] = []
    for spec in tool.schema.args:
        if spec.type == "file":
            fkwargs: dict[str, Any] = {}
            if spec.description:
                fkwargs["description"] = spec.description
            annotation: Any = Annotated[UploadFile, File(**fkwargs)]
            if not spec.required:
                annotation = Annotated[UploadFile | None, File(**fkwargs)]
            params.append(inspect.Parameter(
                spec.name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=inspect.Parameter.empty if spec.required else None,
                annotation=annotation,
            ))
            continue

        kwargs: dict[str, Any] = {}
        desc = spec.description or ""
        if spec.type in _FORM_JSON_TYPES:
            hint = ('JSON-encoded, e.g. "[1, 2, 3]"' if spec.type == "list"
                    else 'JSON-encoded, e.g. {"k": 1}')
            desc = f"{desc}\n\n{hint}" if desc else hint
            ann: Any = str
        elif spec.type == "enum":
            # forms carry strings; the endpoint coerces to the native choice
            ann = str
            kwargs["json_schema_extra"] = {"enum": list(spec.choices or [])}
        else:
            ann = _annotation(spec)
        if desc:
            kwargs["description"] = desc
        annotation = Annotated[ann, Form(**kwargs)]
        params.append(inspect.Parameter(
            spec.name, inspect.Parameter.POSITIONAL_OR_KEYWORD,
            default=inspect.Parameter.empty if spec.required else spec.default,
            annotation=annotation,
        ))
    return params


def make_multipart_endpoint(tool: "Tool", execute) -> Any:
    """Endpoint ``(**form) -> response`` for a file tool.

    Normalizes every scalar itself (via per-arg TypeAdapters) so the same
    endpoint works when FastAPI resolves the form *and* when the fallback
    route calls it directly with raw form values.
    """
    schema: ToolSchema = tool.schema
    adapters = {
        spec.name: TypeAdapter(_annotation(spec))
        for spec in schema.args
        if spec.type != "file"
    }

    async def endpoint(**kwargs):
        args: dict[str, Any] = dict(kwargs)
        for spec in schema.args:
            name = spec.name
            if spec.type == "file":
                if args.get(name) is None and spec.required:
                    return validation_response(
                        [{"name": name, "msg": "required argument missing"}]
                    )
                continue
            if name not in args:
                if spec.required:
                    return validation_response(
                        [{"name": name, "msg": "required argument missing"}]
                    )
                args[name] = spec.default
                continue
            value = args[name]
            if value is None:
                if not spec.nullable:
                    return validation_response(
                        [{"name": name, "msg": "null is not allowed for this argument"}]
                    )
                continue
            try:
                if spec.type in _FORM_JSON_TYPES:
                    if not isinstance(value, str):
                        return validation_response(
                            [{"name": name, "msg": "must be a JSON-encoded string"}]
                        )
                    args[name] = adapters[name].validate_json(value)
                else:
                    args[name] = adapters[name].validate_python(value)
            except PydValidationError as exc:
                return validation_response(items_from_adapter_error(name, exc))
        return await execute(tool, args)

    endpoint.__signature__ = inspect.Signature(build_multipart_params(tool))  # type: ignore[attr-defined]
    endpoint.__name__ = "run_" + tool.id.replace(".", "_")
    return endpoint
