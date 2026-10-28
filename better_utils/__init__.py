"""Better Utils — turn Python functions into a tool server with a dashboard.

    from better_utils import BetterUtils, Router

    app = BetterUtils(title="My Utils")

    text = Router("text")

    @text.tool
    def reverse_string(s: str) -> str:
        \"\"\"Reverses the input.\"\"\"
        return s[::-1]

    app.include_router(text)

Run it with::

    bu run app:app
"""

from .app import BetterUtils
from .executor import ToolError
from .params import File, ImageFile
from .router import Router
from .tool import tool

__all__ = [
    "BetterUtils",
    "Field",
    "File",
    "ImageFile",
    "Router",
    "ToolError",
    "tool",
]

# Field re-export: `from better_utils import Field` for Annotated constraints.
from pydantic import Field

__version__ = "0.2.0"
