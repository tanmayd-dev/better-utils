"""Signature and docstring parsing: Python function -> tool schema.

This module is pure (no I/O, no globals) so it can be unit tested without
booting the server.
"""

from __future__ import annotations

import inspect
import json
import re
import typing
from dataclasses import dataclass, field
from enum import Enum
from typing import get_args, get_origin

from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from . import params as _params

__all__ = ["ArgSpec", "DocInfo", "ToolSchema", "parse_docstring", "parse_tool"]

# Names shown to the UI. Keep in sync with frontend/src/api.ts.
JS_TYPES = ("string", "integer", "number", "boolean", "enum", "list", "dict", "file")

_UNION_ORIGINS = {typing.Union}
try:  # PEP 604 unions (`int | None`) on 3.10+
    import types as _types

    _UNION_ORIGINS.add(_types.UnionType)
except AttributeError:  # pragma: no cover
    pass


@dataclass
class ArgSpec:
    """One tool argument, already mapped to what the UI needs."""

    name: str
    type: str  # one of JS_TYPES
    required: bool = True
    default: typing.Any = None
    default_json: str | None = None  # for list/dict defaults: JSON-encoded
    description: str | None = None
    nullable: bool = False
    choices: list | None = None
    min: float | None = None
    max: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    accept: str | None = None  # file inputs ("image/*", "text/plain", ...)
    file_shape: str | None = None  # internal: "bytes" (File) | "image" (ImageFile)
    items_type: str | None = None  # element type for list args

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "default": self.default,
            "default_json": self.default_json,
            "description": self.description,
            "nullable": self.nullable,
            "choices": self.choices,
            "min": self.min,
            "max": self.max,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "accept": self.accept,
            "items": None if self.items_type is None else {"type": self.items_type},
        }


@dataclass
class ToolSchema:
    """Everything the UI and executor need about one tool."""

    func_name: str
    name: str  # display name
    description: str = ""
    long_description: str = ""
    args: list[ArgSpec] = field(default_factory=list)
    return_hint: str = "json"  # "json" | "text" | "image"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "long_description": self.long_description,
            "args": [a.to_dict() for a in self.args],
        }


# ---------------------------------------------------------------------------
# docstring parsing (Google style)
# ---------------------------------------------------------------------------

_SECTION_NAMES = (
    "Args", "Arguments", "Parameters", "Returns", "Raises", "Yields",
    "Examples", "Example", "Note", "Warnings",
)
_KEYWORD_ALIASES = {"args": "args", "arguments": "args", "parameters": "args"}
_PARAM_LINE_RE = re.compile(r"^\s+(\**[\w.]+)\s*(?:\([^)]*\))?\s*:\s*(.*)$")


@dataclass
class DocInfo:
    description: str = ""
    long_description: str = ""
    params: dict[str, str] = field(default_factory=dict)


def parse_docstring(doc: str | None) -> DocInfo:
    """Extract the first paragraph, remaining prose, and per-arg docs.

    Understands Google-style ``Args:`` sections::

        One-line summary.

        Longer prose paragraph.

        Args:
            text: Input text description.
            count: Optional continuation lines
                are joined with a space.
    """
    info = DocInfo()
    if not doc:
        return info

    prose: list[str] = []  # raw lines of the current prose paragraph
    collected: list[str] = []  # finished prose paragraphs

    section: str | None = None
    param_name: str | None = None
    param_indent = 0
    param_desc_parts: list[str] = []

    def _end_param() -> None:
        nonlocal param_name, param_desc_parts
        if param_name is not None:
            text = " ".join(p for p in (s.strip() for s in param_desc_parts) if p)
            info.params[param_name] = text
            param_name = None
            param_desc_parts = []

    def _finish_paragraph() -> None:
        nonlocal prose
        text = " ".join(l.strip() for l in prose).strip()
        if text:
            collected.append(text)
        prose = []

    for line in doc.splitlines():
        stripped = line.strip()

        header = stripped.rstrip(":")
        if stripped.endswith(":") and header in _SECTION_NAMES:
            _finish_paragraph()
            _end_param()
            section = _KEYWORD_ALIASES.get(header.lower(), header.lower())
            continue

        if section == "args":
            m = _PARAM_LINE_RE.match(line)
            if m:
                _end_param()
                param_name = m.group(1).lstrip("*")
                param_indent = len(line) - len(line.lstrip())
                if m.group(2).strip():
                    param_desc_parts.append(m.group(2).strip())
                continue
            if not stripped:
                _end_param()
                continue
            if param_name is not None and (len(line) - len(line.lstrip())) > param_indent:
                param_desc_parts.append(stripped)
                continue
            # A non-indented line leaves the Args section and is prose again.
            _end_param()
            section = None

        if section in ("returns", "raises", "yields", "examples", "example", "note", "warnings"):
            continue  # skimmed, never rendered

        if stripped:
            prose.append(line)
        else:
            _finish_paragraph()

    _finish_paragraph()
    _end_param()

    if collected:
        info.description = collected[0]
        info.long_description = "\n\n".join(collected[1:])
    return info


# ---------------------------------------------------------------------------
# annotation mapping
# ---------------------------------------------------------------------------

def _load_hints(func: typing.Callable) -> dict:
    """Resolved type hints (works with string annotations), fall back to raw."""
    try:
        return typing.get_type_hints(func, include_extras=True)
    except Exception:
        hints: dict = {}
        for pname, p in inspect.signature(func).parameters.items():
            hints[pname] = p.annotation
        hints["return"] = inspect.signature(func).return_annotation
        return hints


def _split_annotated(ann) -> tuple[typing.Any, list]:
    """(base, metadata) or (ann, [])."""
    if hasattr(ann, "__metadata__"):
        args = get_args(ann)
        return args[0], list(args[1:])
    return ann, []


def _split_union(ann) -> tuple[list | None, bool]:
    """Return (non-None members, nullable) for union types, else (None, False)."""
    origin = get_origin(ann)
    if origin is not None and any(origin is u for u in _UNION_ORIGINS):
        args = get_args(ann)
        nullable = type(None) in args
        return [a for a in args if a is not type(None)], nullable
    return None, False


def _scalar_type_name(t: object) -> str | None:
    if t is str:
        return "string"
    if t is bool:
        return "boolean"
    if t is int:
        return "integer"
    if t is float:
        return "number"
    return None


def _field_bound(field_info: FieldInfo, attrs: tuple[str, ...]) -> float | None:
    """Pull a bound off a FieldInfo or its metadata objects."""
    for attr in attrs:
        val = getattr(field_info, attr, None)
        if val is not None:
            return val
        for meta in field_info.metadata:
            val = getattr(meta, attr, None)
            if val is not None:
                return val
    return None


def _apply_field_info(arg: ArgSpec, field_info: FieldInfo) -> None:
    if field_info.description and not arg.description:
        arg.description = field_info.description
    ge = _field_bound(field_info, ("ge",))
    le = _field_bound(field_info, ("le",))
    gt = _field_bound(field_info, ("gt",))
    lt = _field_bound(field_info, ("lt",))
    if ge is not None:
        arg.min = ge
    elif gt is not None:
        arg.min = _exclusive_to_inclusive(gt, arg.type == "integer", is_min=True)
    if le is not None:
        arg.max = le
    elif lt is not None:
        arg.max = _exclusive_to_inclusive(lt, arg.type == "integer", is_min=False)
    if arg.type == "string":
        ml = _field_bound(field_info, ("min_length",))
        xl = _field_bound(field_info, ("max_length",))
        if ml is not None:
            arg.min_length = ml
        if xl is not None:
            arg.max_length = xl


def _int_or_float(value: float, integral: bool) -> float:
    if integral and float(value).is_integer():
        return int(value)
    return value


def _exclusive_to_inclusive(value: float, integral: bool, *, is_min: bool) -> float:
    """Convert a strict bound (gt/lt) to the closest inclusive one the UI knows."""
    if not integral:
        return value
    shifted = value + (1 if is_min else -1)
    return int(shifted) if float(shifted).is_integer() else shifted


def _json_safe(default: typing.Any, arg: ArgSpec) -> typing.Any:
    if default is None or isinstance(default, (bool, str)):
        return default
    if isinstance(default, Enum):
        return default.value
    if isinstance(default, dict):
        return dict(default)
    if isinstance(default, (list, tuple)):
        return list(default)
    if isinstance(default, float):
        return default
    if isinstance(default, int):
        return default
    return str(default)


def _first_field_info(metadata) -> FieldInfo | None:
    for m in metadata:
        if isinstance(m, FieldInfo):
            return m
    return None


def _map_single(t, arg: ArgSpec) -> str:
    origin = get_origin(t)

    if origin is typing.Literal:
        arg.choices = list(get_args(t))
        return "enum"
    if isinstance(t, type) and issubclass(t, Enum):
        arg.choices = [m.value for m in t]
        return "enum"

    if origin is list:
        args = get_args(t)
        if args:
            inner_base, _meta = _split_annotated(args[0])
            arg.items_type = _scalar_type_name(inner_base) or "string"
        return "list"

    if origin is dict or t is dict:
        return "dict"

    if _params.is_file_type(t):
        arg.type = "file"
        arg.accept = getattr(t, "accept", None)
        arg.file_shape = "image" if _is_image_marker(t) else "bytes"
        return "file"

    name = _scalar_type_name(t)
    if name:
        return name

    return "string"


def _map_annotation(param_name: str, ann, param_default, doc_param: str | None) -> ArgSpec:
    arg = ArgSpec(name=param_name, type="string", required=True, description=doc_param)

    # A pydantic Field used as the *default* still describes the argument.
    default_field_info = None
    if isinstance(param_default, FieldInfo):
        default_field_info = param_default
        if param_default.default is not PydanticUndefined:
            param_default = param_default.default
        else:
            # Field() with no default, or with a default_factory: required arg
            param_default = inspect.Parameter.empty

    base, metadata = _split_annotated(ann)
    field_info = default_field_info or _first_field_info(metadata)

    members, nullable = _split_union(base)
    if members:
        member = members[0]
        arg.nullable = nullable
        if member is not None:
            arg.type = _map_single(member, arg)
    else:
        arg.type = _map_single(base, arg)

    if param_default is inspect.Parameter.empty:
        arg.required = not arg.nullable
        arg.default = None
    else:
        arg.required = False
        arg.default = _json_safe(param_default, arg)

    if arg.type in ("list", "dict") and arg.default is not None:
        try:
            arg.default_json = json.dumps(arg.default)
        except (TypeError, ValueError):
            arg.default_json = None

    if field_info is not None:
        _apply_field_info(arg, field_info)
    return arg


def parse_tool(func: typing.Callable, *, name: str | None = None) -> ToolSchema:
    """Build a :class:`ToolSchema` from a function's signature and docstring."""
    hints = _load_hints(func)
    doc = parse_docstring(inspect.getdoc(func))

    args: list[ArgSpec] = []
    for param_name, param in inspect.signature(func).parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        annotation = hints.get(param_name, param.annotation)
        args.append(_map_annotation(param_name, annotation, param.default, doc.params.get(param_name)))

    ret = hints.get("return", inspect.Parameter.empty)
    hint = "json"
    if ret is not inspect.Parameter.empty:
        base, _meta = _split_annotated(ret)
        members, _nullable = _split_union(base)
        first = members[0] if members else base
        if _params.is_file_type(first) and _is_image_marker(first) or is_pil_image(first):
            hint = "image"
        elif getattr(first, "__name__", None) == "str":
            hint = "text"

    return ToolSchema(
        func_name=func.__name__,
        name=name or getattr(func, "_tool_name", None) or func.__name__,
        description=doc.description,
        long_description=doc.long_description,
        args=args,
        return_hint=hint,
    )


def _is_image_marker(t) -> bool:
    try:
        if isinstance(t, type) and issubclass(t, _params.ImageFile):
            return True
    except TypeError:
        return False
    return t is _params.ImageFile


def is_pil_image(t) -> bool:
    """True when the annotation is PIL's Image type (return hints)."""
    try:
        from PIL import Image

        return t is Image.Image
    except Exception:
        return False
