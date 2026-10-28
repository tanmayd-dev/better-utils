"""Text tools: scalars, enums, and docstring rendering."""

from typing import Literal

from better_utils import Router

text = Router("text")


@text.tool(name="Reverse Text")
def reverse_string(text: str) -> str:
    """Reverses the input text character by character."""
    return text[::-1]


@text.tool(name="Word Count")
def count_words(text: str, unique_only: bool = False) -> dict:
    """Counts words in the given text.

    Args:
        text: The text to analyze.
        unique_only: Only count distinct words.
    """
    words = text.split()
    if unique_only:
        words = list(dict.fromkeys(words))
    return {"words": len(words), "distinct": len({w.lower() for w in text.split()})}


@text.tool(name="Slugify")
def slugify(text: str, case: Literal["lower", "upper", "title"] = "lower") -> str:
    """Turns arbitrary text into a URL-safe slug."""
    slug = "".join(c if c.isalnum() else "-" for c in text.strip().lower()).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    if case == "upper":
        return slug.upper()
    if case == "title":
        return slug.title()
    return slug
