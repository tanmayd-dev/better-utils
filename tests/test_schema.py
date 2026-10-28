"""Schema construction: annotations, docstrings, constraints."""

from enum import Enum
from typing import Annotated, Literal

from pydantic import Field

from better_utils.params import File, ImageFile
from better_utils.schema import parse_tool


class Tea(Enum):
    GREEN = "green"
    BLACK = "black"


def test_scalar_mapping():
    def f(a: str, b: bool, c: int, d: float):
        pass

    schema = parse_tool(f)
    assert [a.type for a in schema.args] == ["string", "boolean", "integer", "number"]
    assert all(a.required for a in schema.args)


def test_bare_tool_decorator_marks_function():
    """Regression: the old framework registered NOTHING when @tool was bare."""
    from better_utils.tool import is_tool, tool

    @tool
    def lower(s: str) -> str:
        return s.lower()

    def recovered(s: str) -> str: ...

    tool(recovered)

    assert is_tool(lower) and is_tool(recovered)
    assert inspect_signature_ok(lower)


def inspect_signature_ok(func) -> bool:
    import inspect

    return list(inspect.signature(func).parameters) == ["s"]


def test_optional_and_unions():
    def f(a: int | None = None, b: int | None = None, c: float | None = 1.5):
        pass

    schema = parse_tool(f)
    a, b, c = schema.args
    assert a.type == "integer" and a.nullable and not a.required
    assert b.type == "integer" and b.nullable and not b.required
    assert c.type == "number" and c.default == 1.5 and not c.required


def test_list_and_dict():
    def f(vals: list[float], tags: list[str] | None = None, conf: dict | None = None):
        pass

    schema = parse_tool(f)
    assert schema.args[0].type == "list" and schema.args[0].items_type == "number"
    assert schema.args[1].items_type == "string"
    assert schema.args[2].type == "dict"


def test_enum_and_literal():
    def f(mode: Literal["fast", "slow"] = "fast", tea: Tea = Tea.BLACK):
        pass

    schema = parse_tool(f)
    assert schema.args[0].type == "enum" and schema.args[0].choices == ["fast", "slow"]
    assert schema.args[1].choices == ["green", "black"]
    assert schema.args[1].default == "black"  # enum defaults become their value


def test_field_bounds_no_epsilon_lies():
    """Old parser reported ge as min and fudged gt by +0.0001; don't."""
    def f(n: Annotated[int, Field(ge=1, le=100)], x: Annotated[float, Field(gt=0)] = 1.0):
        pass

    schema = parse_tool(f)
    n, x = schema.args
    assert n.min == 1 and n.max == 100
    # strict gt on floats: the bound is reported as-is (an exclusive bound),
    # never silently nudged
    assert x.min == 0
    # integer exclusive bounds snap to the nearest includable integer
    def g(k: Annotated[int, Field(gt=4)] = 5): ...
    assert parse_tool(g).args[0].min == 5


def test_field_as_default_value():
    def f(count: int = Field(5, ge=1, description="How many")):
        pass

    schema = parse_tool(f)
    arg = schema.args[0]
    assert arg.required is False and arg.default == 5
    assert arg.min == 1 and arg.description == "How many"


def test_docstring_param_docs_and_return_hint():
    def f(text: str, times: int = 2) -> str:
        """Creates filler.

        Longer usage notes here.

        Args:
            text: The base text,
                spanning multiple lines.
            times: Repetitions.

        Returns:
            The result text.
        """
        return text * times

    schema = parse_tool(f)
    assert schema.description == "Creates filler."
    assert schema.long_description == "Longer usage notes here."
    assert schema.args[0].description == "The base text, spanning multiple lines."
    assert schema.args[1].description == "Repetitions."
    assert schema.return_hint == "text"


def test_file_marshals():
    def f(img: ImageFile, blob: File | None = None):
        pass

    schema = parse_tool(f)
    img, blob = schema.args
    assert img.type == "file" and img.accept == "image/*" and img.required
    assert blob.type == "file" and blob.accept == "*/*" and not blob.required


def test_defaults_preserved():
    def f(speed: float = 0.5, label: str = "x", big: bool = True, step: int = 3):
        pass

    schema = parse_tool(f)
    assert [a.default for a in schema.args] == [0.5, "x", True, 3]
    assert not any(a.required for a in schema.args)
