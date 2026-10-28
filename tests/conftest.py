import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from better_utils import BetterUtils


def write_tools(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content))
    return root


@pytest.fixture
def build_app(tmp_path: Path):
    """Factory: write tool files, build the app, return (client, app)."""
    calls: list = []

    def _make(files: dict[str, str], *, settings: dict | None = None):
        tools_root = tmp_path / f"tools_{len(calls)}"
        calls.append(tools_root)
        write_tools(tools_root, files)
        app = BetterUtils(title="test utils", tools_dir=str(tools_root))
        for key, value in (settings or {}).items():
            setattr(app.settings, key, value)
        fastapi_app = app.build()
        return TestClient(fastapi_app), app

    return _make


@pytest.fixture
def png_bytes() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (100, 60), "tomato").save(buf, format="PNG")
    return buf.getvalue()
