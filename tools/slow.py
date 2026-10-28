"""A slow, asynchronous tool: proves the event loop never blocks."""

import asyncio

from better_utils import Router

slow = Router("slow")


@slow.tool(name="Slow Echo")
async def slow_echo(seconds: float = 4.0, message: str = "done") -> str:
    """Sleeps for ``seconds`` and echoes back.

    While this runs, other requests are served normally — the tool sleeps in
    its own task instead of blocking the server.
    """
    await asyncio.sleep(seconds)
    return f"slow echo: {message}"
