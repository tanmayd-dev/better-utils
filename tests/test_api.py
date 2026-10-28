"""HTTP contract tests against a real app (TestClient)."""

import asyncio
import time

import httpx
from starlette.testclient import TestClient

from better_utils import BetterUtils

ECHO = """\
from better_utils import tool

@tool(name="Echo")
def echo(text: str, times: int = 1) -> list[str]:
    '''Echoes input text twice.'''
    return [text] * times

@tool(name="Sum List")
def sum_values(values: list[float]) -> float:
    '''sums values'''
    return sum(values)

@tool
def maybe_fail(mode: str = "ok") -> dict:
    '''fails on demand'''
    if mode == "boom":
        raise ValueError("deliberate boom")
    if mode == "toolerror":
        from better_utils import ToolError
        raise ToolError("clean message")
    if mode == "sleep":
        import time
        time.sleep(5)
    return {"mode": mode}
"""

ASYNC_TOOL = """\
import asyncio
from better_utils import tool

@tool
async def sleepy(seconds: float = 1.0, note: str = "done") -> str:
    '''sleeps in its own task'''
    await asyncio.sleep(seconds)
    return note
"""

IMAGE_TOOL = """\
from PIL import Image, ImageDraw
from better_utils import ImageFile, tool

@tool
def connect(img: ImageFile, draw: bool = False) -> Image.Image:
    '''returns the uploaded image, optionally with crosshair lines'''
    if draw:
        d = ImageDraw.Draw(img)
        d.line([(0, 0), (img.width, img.height)], fill="black", width=3)
    return img
"""


def make_client(files: dict[str, str], *, settings: dict | None = None) -> tuple[TestClient, BetterUtils]:
    import tempfile
    from pathlib import Path

    from .conftest import write_tools

    root = Path(tempfile.mkdtemp(prefix="bu_tools_"))
    write_tools(root, files)
    app = BetterUtils(title="api tests", tools_dir=str(root))
    for key, value in (settings or {}).items():
        setattr(app.settings, key, value)
    return TestClient(app.build()), app


def test_health_and_tools_listing():
    client, _ = make_client({"alpha.py": ECHO})
    health = client.get("/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert health.json()["tools"] == 3

    body = client.get("/api/tools").json()
    tools = {t["id"]: t for t in body["tools"]}
    # alpha.gets: echo / sum_values / maybe_fail
    assert set(tools) == {"alpha.echo", "alpha.sum_values", "alpha.maybe_fail"}
    echo = tools["alpha.echo"]
    arg_names = [a["name"] for a in echo["args"]]
    assert arg_names == ["text", "times"]
    etext = echo["args"][0]
    assert etext["type"] == "string" and etext["required"]
    assert etext.get("description") is None  # docstring has no Args section

    values = tools["alpha.sum_values"]["args"][0]
    assert values["type"] == "list" and values["items"]["type"] == "number"
    maybe_fail = tools["alpha.maybe_fail"]["args"][0]
    assert maybe_fail["type"] == "string" and not maybe_fail["required"] and maybe_fail["default"] == "ok"


def test_run_json_envelope():
    client, _ = make_client({"alpha.py": ECHO})

    r = client.post("/api/run/alpha.echo", json={"text": "hello", "times": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["type"] == "json"
    assert body["data"] == ["hello", "hello"]
    assert body["elapsed_ms"] >= 0

    r2 = client.post("/api/run/alpha.echo", json={"text": "hello"})
    assert r2.status_code == 200
    assert r2.json()["data"] == ["hello"]


def test_run_text_return_type_hint():
    client, _ = make_client({"alpha.py": ECHO})
    r = client.post("/api/run/alpha.sum_values", json={"values": [1.5, 2.5]})
    assert r.status_code == 200
    assert r.json()["data"] == 4.0


def test_validation_422_shape():
    client, _ = make_client({"alpha.py": ECHO})

    # missing required arg
    r = client.post("/api/run/alpha.echo", json={"times": 2})
    assert r.status_code == 422
    body = r.json()
    assert body["ok"] is False and body["error"] == "Validation failed"
    assert any(v["name"] == "text" for v in body["validation"])

    # bad list element
    r2 = client.post("/api/run/alpha.sum_values", json={"values": [1, "x"]})
    assert r2.status_code == 422
    assert "values" in r2.json()["validation"][0]["name"] or r2.json()["validation"][0].get("msg")

    # unknown field
    r3 = client.post("/api/run/alpha.echo", json={"text": "hi", "nope": 1})
    assert r3.status_code == 422
    assert r3.json()["validation"][0]["name"] == "nope"


def test_not_found():
    client, _ = make_client({"alpha.py": ECHO})
    r = client.post("/api/run/none.nothing", json={})
    assert r.status_code == 404


def test_toolerror_400_and_exception_500():
    client, _ = make_client({"alpha.py": ECHO})

    r = client.post("/api/run/alpha.maybe_fail", json={"mode": "toolerror"})
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert "clean message" in r.json()["error"]
    assert "traceback" not in r.json()

    r2 = client.post("/api/run/alpha.maybe_fail", json={"mode": "boom"})
    assert r2.status_code == 500
    assert r2.json()["traceback"] and "deliberate boom" in r2.json()["error"]


def test_timeout_504():
    client, _ = make_client({"alpha.py": ECHO}, settings={"timeout_s": 0.3})
    t0 = time.perf_counter()
    r = client.post("/api/run/alpha.maybe_fail", json={"mode": "sleep"})
    elapsed = time.perf_counter() - t0
    assert r.status_code == 504
    assert "timeout" in r.json()["error"].lower()
    assert elapsed < 2.0  # 5s sleep cut short


def test_async_tool_nonblocking():
    """Slow sync tool must not freeze other requests (thread-pool execution)."""
    from better_utils.tool import tool as mark

    app = BetterUtils(title="async")
    fastapi_app = app.build()
    registry = app.registry

    def sleeper(seconds: float = 1.0) -> str:
        '''sleeps'''
        import time as _t
        _t.sleep(seconds)
        return "slept"

    mark(sleeper)
    registry.register_callable(sleeper, tool_id="sleeper", group="Sync")

    async def scenario():
        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as cx:
            slow_task = asyncio.create_task(
                cx.post("/api/run/sleeper", json={"seconds": 1.0})
            )
            await asyncio.sleep(0.15)  # slow call reaches the thread pool
            t0 = time.perf_counter()
            ping = await cx.get("/health")
            ping_ms = time.perf_counter() - t0
            run = await slow_task
            return ping, ping_ms, run

    ping, ping_ms, run = asyncio.run(scenario())
    assert ping.status_code == 200
    assert ping_ms < 0.5  # health answered DURING the sleep
    assert run.status_code == 200 and run.json()["data"] == "slept"


def test_async_tool_endpoint():
    client, _ = make_client({"slow.py": ASYNC_TOOL})
    r = client.post("/api/run/slow.sleepy", json={"seconds": 0.05, "note": "fast"})
    assert r.status_code == 200
    assert r.json()["data"] == "fast"


def test_image_tool_multipart_and_artifact(png_bytes):
    client, _ = make_client({"img.py": IMAGE_TOOL})
    r = client.post(
        "/api/run/img.connect",
        files={"img": ("photo.png", png_bytes, "image/png")},
        data={"draw": "true"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["type"] == "image"
    assert body["image_url"].startswith("/api/artifacts/")
    art = client.get(body["image_url"])
    assert art.status_code == 200
    assert art.headers["content-type"] == "image/png"
    assert art.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_image_rejects_non_image_content_type(png_bytes):
    client, _ = make_client({"img.py": IMAGE_TOOL})
    r = client.post(
        "/api/run/img.connect",
        files={"img": ("doc.txt", b"plain text", "text/plain")},
    )
    assert r.status_code == 422
    assert any(v["name"] == "img" for v in r.json()["validation"])


def test_checksum_multipart():
    CHECKSUM = """\
import hashlib
from better_utils import File, tool

@tool
def sha256_sum(file: File) -> dict:
    '''hashes an uploaded file'''
    return {"sha256": hashlib.sha256(file).hexdigest(), "bytes": len(file)}
"""
    client, _ = make_client({"chk.py": CHECKSUM})
    r = client.post(
        "/api/run/chk.sha256_sum",
        files={"file": ("x.bin", b"hello", "application/octet-stream")},
    )
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["bytes"] == 5
    assert body["sha256"][:12] == "2cf24dba5fb0"


def test_no_tests_vs_passing_tests():
    NO_TESTS_TOOL = """\
from better_utils import tool

@tool
def untethered(text: str = "fine") -> str:
    '''a tool that has never seen a test'''
    return text
"""
    PASSING = """\
from better_utils import tool

@tool
def echo(text: str = "hi") -> str:
    '''echo'''
    return text
"""
    TEST = """\
import echo

def test_echo():
    assert echo.echo("x") == "x"

def test_other():
    assert echo.echo("y") == "y"
"""
    client, _ = make_client({
        "lonely.py": NO_TESTS_TOOL,
        "echo.py": PASSING,
        "tests/test_echo.py": TEST,
    })

    r = client.post("/api/test/lonely.untethered")
    assert r.status_code == 200
    assert r.json()["status"] == "no_tests"

    r_pass = client.post("/api/test/echo.echo")
    assert r_pass.status_code == 200
    body = r_pass.json()
    assert body["status"] == "passed"
    assert body["passed"] == 2 and body["failed"] == 0
    assert body["duration_ms"] >= 0


def test_failing_tests_reported():
    FAILING = """\
from better_utils import tool

@tool
def echo(text: str = "hi") -> str:
    '''echo'''
    return text
"""
    TEST = """\
import echo

def test_echo():
    assert echo.echo("x") == "WRONG"
"""
    client, _ = make_client({"echo.py": FAILING, "tests/test_echo.py": TEST})
    r = client.post("/api/test/echo.echo")
    body = r.json()
    assert body["status"] == "failed"
    assert body["failed"] == 1
    assert "WRONG" in body["output"] or "test_echo" in body["output"]


def test_load_errors_listed():
    client, _ = make_client({"alpha.py": ECHO, "broken.py": "this is { not python"})
    body = client.get("/api/tools").json()
    assert len(body["errors"]) == 1
    assert body["errors"][0]["path"] == "broken.py"
    assert body["tools"]  # tool still listed


# ---------------------------------------------------------------------------
# per-tool documented routes (generated Pydantic models)
# ---------------------------------------------------------------------------

CONF = """\
from typing import Annotated, Literal
from better_utils import Field, tool

@tool
def grade(score: Annotated[int, Field(ge=0, le=100)], level: Literal["low", "high"] = "low",
          note: Annotated[str, Field(min_length=2, max_length=5)] = "ok") -> dict:
    '''Grades things.'''
    return {"score": score, "level": level, "note": note}
"""

NULLABLE = """\
from better_utils import tool

@tool
def probe(anchor: float | None = None, label: str | None = None) -> dict:
    '''probes.'''
    return {"anchor": anchor, "label": label}
"""

STAMP = """\
from PIL import Image
from better_utils import ImageFile, tool

@tool
def stamp(img: ImageFile, positions: list[float] | None = None) -> Image.Image:
    '''stamps positions on the image.'''
    return img
"""

PICK = """\
from typing import Literal
from better_utils import ImageFile, tool

@tool
def mark(img: ImageFile, size: Literal[1, 2, 3] = 2) -> dict:
    '''marks a size.'''
    return {"size": size}
"""


def test_openapi_documents_per_tool_schemas():
    client, _ = make_client({"alpha.py": ECHO, "conf.py": CONF, "img.py": IMAGE_TOOL})
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]

    # per-tool routes are in the spec, the 404 catch-all is not
    assert "/api/run/alpha.echo" in paths and "/api/run/conf.grade" in paths
    assert "/api/run/{tool_id}" not in paths
    assert "RunResponse" in spec["components"]["schemas"]

    schemas = spec["components"]["schemas"]
    post = paths["/api/run/conf.grade"]["post"]
    assert post["summary"] == "grade"
    assert "Grades things." in (post.get("description") or "")

    body_ref = post["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    model = schemas[body_ref.split("/")[-1]]
    assert model["required"] == ["score"]
    props = model["properties"]
    assert props["score"]["type"] == "integer"
    assert props["score"]["minimum"] == 0 and props["score"]["maximum"] == 100
    level = props["level"]
    if "allOf" in level:  # schema variants across FastAPI/Pydantic versions
        level = level["allOf"][0]
    assert set(level["enum"]) == {"low", "high"}
    assert props["note"]["minLength"] == 2
    assert props["note"]["maxLength"] == 5
    assert props["note"]["default"] == "ok"

    # tools are grouped by tag, mirroring the dashboard sidebar
    catalog = {t["id"]: t for t in client.get("/api/tools").json()["tools"]}
    assert post["tags"] == [catalog["conf.grade"]["group"]]

    # file tools document their multipart form fields
    img_body = paths["/api/run/img.connect"]["post"]["requestBody"]["content"]
    assert "multipart/form-data" in img_body
    img_schema = img_body["multipart/form-data"]["schema"]
    if "$ref" in img_schema:  # FastAPI hoists form params into a Body_ model
        img_schema = schemas[img_schema["$ref"].split("/")[-1]]
    img_props = img_schema["properties"]
    assert img_props["img"]["type"] == "string"  # upload slot (binary body)
    assert img_schema["required"] == ["img"]
    assert img_props["draw"]["type"] == "boolean"


def test_docs_pages_served():
    client, _ = make_client({"alpha.py": ECHO})
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_typed_route_bounds_and_enum():
    client, _ = make_client({"conf.py": CONF})

    ok = client.post("/api/run/conf.grade", json={"score": 90, "level": "high"})
    assert ok.status_code == 200 and ok.json()["data"]["level"] == "high"

    # string form of an int-valued choice still coerces to the native value
    coerced = client.post("/api/run/conf.grade", json={"score": 1, "level": "low"})
    assert coerced.status_code == 200 and coerced.json()["data"]["level"] == "low"

    out_of_range = client.post("/api/run/conf.grade", json={"score": 150})
    assert out_of_range.status_code == 422
    assert out_of_range.json()["validation"][0]["name"] == "score"

    bad_choice = client.post("/api/run/conf.grade", json={"score": 1, "level": "meh"})
    assert bad_choice.status_code == 422
    assert bad_choice.json()["validation"][0]["name"] == "level"

    bad_len = client.post("/api/run/conf.grade", json={"score": 1, "note": "way too long"})
    assert bad_len.status_code == 422
    assert bad_len.json()["validation"][0]["name"] == "note"


def test_nullable_args_accept_none():
    client, _ = make_client({"nul.py": NULLABLE})
    r = client.post("/api/run/nul.probe", json={"anchor": None, "label": None})
    assert r.status_code == 200
    assert r.json()["data"] == {"anchor": None, "label": None}

    r2 = client.post("/api/run/nul.probe", json={})
    assert r2.status_code == 200
    assert r2.json()["data"] == {"anchor": None, "label": None}


def test_multipart_json_list_arg(png_bytes):
    client, _ = make_client({"img.py": STAMP})

    r = client.post(
        "/api/run/img.stamp",
        files={"img": ("p.png", png_bytes, "image/png")},
        data={"positions": "[0.5, 2]"},
    )
    assert r.status_code == 200 and r.json()["ok"]

    bad = client.post(
        "/api/run/img.stamp",
        files={"img": ("p.png", png_bytes, "image/png")},
        data={"positions": "not json"},
    )
    assert bad.status_code == 422
    assert bad.json()["validation"][0]["name"] == "positions"

    item = client.post(
        "/api/run/img.stamp",
        files={"img": ("p.png", png_bytes, "image/png")},
        data={"positions": '["a", 1]'},
    )
    assert item.status_code == 422
    first = item.json()["validation"][0]
    assert first["name"] == "positions" and "item 0" in first["msg"]


def test_multipart_enum_string_coercion(png_bytes):
    client, _ = make_client({"pick.py": PICK})
    r = client.post(
        "/api/run/pick.mark",
        files={"img": ("p.png", png_bytes, "image/png")},
        data={"size": "3"},
    )
    assert r.status_code == 200
    assert r.json()["data"] == {"size": 3}  # native int, not "3"


def test_late_registered_multipart_tool(png_bytes):
    """Tools registered after build() run through the fallback route."""
    from PIL import Image

    from better_utils import ImageFile
    from better_utils.tool import tool as mark_tool

    def stamp(img: ImageFile, positions: list[float] | None = None) -> Image.Image:
        '''stamps marks on the image'''
        return img

    app = BetterUtils(title="late")
    fa = app.build()
    mark_tool(stamp)
    app.registry.register_callable(stamp, tool_id="late.stamp", group="Late")

    client = TestClient(fa)
    r = client.post(
        "/api/run/late.stamp",
        files={"img": ("p.png", png_bytes, "image/png")},
        data={"positions": "[1, 2]"},
    )
    assert r.status_code == 200 and r.json()["type"] == "image"
