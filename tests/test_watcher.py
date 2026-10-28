"""Watcher integration: real filesystem events through the debounced handler."""

import time
from pathlib import Path

from better_utils import BetterUtils
from better_utils.watcher import start_watcher

from .conftest import write_tools

TOOL_A = """\
from better_utils import tool

@tool
def hello(name: str = "a") -> str:
    '''Greets A.'''
    return "A"
"""

TOOL_B = """\
from better_utils import tool

@tool
def hello(name: str = "b") -> dict:
    '''Greets B.'''
    return {"b": name}
"""

TOOL_C = """\
from better_utils import tool

@tool
def hello2() -> dict:
    '''Greets C.'''
    return {"c": True}
"""


def wait_for(predicate, timeout=8.0, step=0.2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def test_watcher_reload_and_delete(tmp_path: Path):
    tools = tmp_path / "tools"
    write_tools(tools, {"alpha.py": TOOL_A})

    app = BetterUtils(title="watch", tools_dir=str(tools))
    app.settings.reload = True
    _ = app.build()
    observer = start_watcher(
        lambda: app.registry, on_change=lambda: app.on_registry_changed()
    )
    assert observer is not None

    from starlette.testclient import TestClient

    client = TestClient(app._built)

    try:
        target = tools / "alpha.py"
        target.write_text(TOOL_B)  # modify: schema changes
        assert wait_for(
            lambda: "alpha.hello" in {t.id for t in app.registry.list_tools()}
        )
        # deeper edit visible in schema
        assert wait_for(
            lambda: next(
                (t for t in app.registry.list_tools() if t.id == "alpha.hello"),
                None,
            ).schema.description == "Greets B."
        )

        created = tools / "beta.py"
        created.write_text(TOOL_C)  # create new file → new tool appears
        assert wait_for(
            lambda: "beta.hello2" in {t.id for t in app.registry.list_tools()}
        )
        # route table + openapi followed the registry
        r = client.post("/api/run/beta.hello2", json={})
        assert r.status_code == 200 and r.json()["data"] == {"c": True}
        assert "/api/run/beta.hello2" in client.get("/openapi.json").json()["paths"]

        created.unlink()  # deletion → pruned, not zombie
        assert wait_for(
            lambda: "beta.hello2" not in {t.id for t in app.registry.list_tools()}
        )
        assert wait_for(
            lambda: client.post("/api/run/beta.hello2", json={}).status_code == 404
        )
    finally:
        observer.stop()
        observer.join(timeout=5)


def test_watcher_ignores_outside_roots(tmp_path: Path):
    tools = tmp_path / "tools"
    write_tools(tools, {"alpha.py": TOOL_A})
    app = BetterUtils(title="watch2", tools_dir=str(tools))
    _ = app.build()
    observer = start_watcher(lambda: app.registry)
    try:
        stranger = tmp_path / "elsewhere.py"
        stranger.write_text(TOOL_B)
        time.sleep(0.6)  # well past the debounce window
        ids = {t.id for t in app.registry.list_tools()}
        assert ids == {"alpha.hello"}
    finally:
        observer.stop()
        observer.join(timeout=5)
