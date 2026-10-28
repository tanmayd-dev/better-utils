"""Example BetterUtils app.

Run with::

    bu run example_app:app
"""

from better_utils import BetterUtils, Router

app = BetterUtils(title="Better Utils — Examples", tools_dir="tools")

# Routers can also register tools defined right here (no file discovery).
bookmarks = Router("bookmarks")


@bookmarks.tool(name="Add Bookmark")
def add_bookmark(url: str, tags: list[str] | None = None) -> dict:
    """Stores a URL (demo tool: it only reports what it would store).

    Args:
        url: The page to bookmark.
        tags: Optional tags for the bookmark.
    """
    return {"url": url, "tags": tags or []}

app.include_router(bookmarks)
