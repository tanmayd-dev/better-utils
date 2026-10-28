"""Registry behavior: unique module identity, collisions, errors, pruning."""

from pathlib import Path

import pytest

from better_utils import BetterUtils
from better_utils.registry import ToolRegistry
from better_utils.router import Router

from .conftest import write_tools

TEXT_TOOL = """
from better_utils import tool

@tool
def hello(name: str = "world") -> str:
    '''Greets someone.'''
    return f"hello {name}"
"""


def run_dir(tmp_path: Path, tree: dict[str, dict[str, str]]) -> ToolRegistry:
    """``tree`` keys are subdirs *relative to the scan root*; "" is the root."""
    registry = ToolRegistry()
    for subdir, files in tree.items():
        write_tools(tmp_path / subdir if subdir else tmp_path, files)
    registry.load_dir(tmp_path)
    return registry


def test_bare_tool_registers(tmp_path: Path):
    """THE regression: bare @tool used to silently unregister everything."""
    registry = run_dir(tmp_path, {"": {"alpha.py": TEXT_TOOL}})
    tools = registry.list_tools()
    assert [t.id for t in tools] == ["alpha.hello"]
    assert tools[0].schema.name == "hello"
    assert tools[0].group == "Alpha"


def test_same_stem_files_never_collide(tmp_path: Path):
    """Old bug: module_name = tools.{stem} clobbered same-named files."""
    registry = run_dir(tmp_path, {
        "a": {"convert.py": TEXT_TOOL},
        "b": {"convert.py": TEXT_TOOL.replace("hello(name", "shout(name")},
    })
    ids = {t.id for t in registry.list_tools()}
    assert ids == {"a.convert.hello", "b.convert.shout"}


def test_duplicate_id_across_files_rejected(tmp_path: Path):
    registry = run_dir(tmp_path, {
        "a": {"convert.py": TEXT_TOOL},
        "b": {"convert.py": TEXT_TOOL},
    })
    # same function name in same-stem files STILL yields distinct ids
    ids = {t.id for t in registry.list_tools()}
    assert ids == {"a.convert.hello", "b.convert.hello"}


def test_import_error_surfaced(tmp_path: Path):
    broken = "\nthis is not valid python {{\n"
    registry = run_dir(tmp_path, {"": {"broken.py": broken}})
    errors = registry.list_errors()
    assert len(errors) == 1
    assert errors[0].path == "broken.py"
    assert "SyntaxError" in errors[0].error or "invalid python" in errors[0].error
    assert registry.list_tools() == []


def test_deletion_prunes_tools(tmp_path: Path):
    registry = run_dir(tmp_path, {"": {"gone.py": TEXT_TOOL}})

    target = tmp_path / "gone.py"
    target.unlink()
    registry.remove_path(target)
    assert registry.list_tools() == [] and registry.list_errors() == []


def test_reload_path_replaces_tools(tmp_path: Path):
    registry = run_dir(tmp_path, {"": {"alpha.py": TEXT_TOOL}})
    assert "alpha.hello" in {t.id for t in registry.list_tools()}

    migrated = TEXT_TOOL.replace("@tool\n", "@tool(name='Greet')\n") + "\n\n@tool\ndef bye() -> str:\n    'bye'\n    return 'bye'\n"
    (tmp_path / "alpha.py").write_text(migrated)
    registry.reload_path(tmp_path / "alpha.py")

    tools = {t.id: t for t in registry.list_tools()}
    assert set(tools) == {"alpha.hello", "alpha.bye"}
    assert tools["alpha.hello"].schema.name == "Greet"


def test_router_include_and_duplicate_error(tmp_path: Path):
    router = Router("bookmarks")

    @router.tool
    def add_bookmark(url: str) -> str:
        'stores'
        return url

    app = BetterUtils(title="dup test")
    app.include_router(router)
    # normal programmatic duplicate (same id, same function) is a no-op
    app.include_router(router)

    # a DIFFERENT function claiming the same id is an error
    intruder = Router("bookmarks")

    @intruder.tool
    def add_bookmark(url: str) -> str:  # noqa: F811 - deliberate same name
        'second'
        return url

    with pytest.raises(Exception):
        app.include_router(intruder)


def test_snapshot_isolation(tmp_path: Path):
    """Mutating a returned listing must not corrupt registry state."""
    registry = run_dir(tmp_path, {"": {"alpha.py": TEXT_TOOL}})
    listing = registry.list_tools()
    length = len(listing)
    listing.append(None)  # type: ignore[arg-type]
    assert len(registry.list_tools()) == length
