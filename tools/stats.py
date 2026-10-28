"""Numeric tools, including the list-argument regression case."""

from typing import Annotated

from pydantic import Field

from better_utils import Router

stats = Router("stats")


@stats.tool
def summarize(values: list[float]) -> dict:
    """Basic descriptive statistics for a list of numbers.

    Args:
        values: Numbers to summarize (JSON array).
    """
    if not values:
        return {"error": "no values provided"}
    return {
        "count": len(values),
        "sum": sum(values),
        "average": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


@stats.tool(name="Fibonacci")
def fib(members: Annotated[int, Field(ge=1, le=64)] = 10) -> list[int]:
    """First ``members`` Fibonacci numbers (the bound drives a UI slider)."""
    seq: list[int] = []
    a, b = 0, 1
    for _ in range(members):
        seq.append(a)
        a, b = b, a + b
    return seq
