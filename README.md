# Better Utils

Better Utils turns Python functions into a tool server with a dashboard. Type
hints become form fields, docstrings become the documentation, and `bu run`
serves everything: a JSON API (one endpoint per tool) plus a bundled React UI
for running, testing, and inspecting tools in the browser.

```python
# app.py
from better_utils import BetterUtils, Router

app = BetterUtils(title="My Utils")

text = Router("text")

@text.tool(name="Reverse Text")
def reverse_string(text: str) -> str:
    """Reverses the input text."""
    return text[::-1]

app.include_router(text)
```

```
$ pip install better-utils
$ bu run app:app
```

Open http://127.0.0.1:8000 — the dashboard is embedded in the wheel; there is
no Node toolchain, no static folder to ship, nothing to configure.

## Writing tools

Tools are plain functions. Everything is derived from the signature and the
docstring (Google style):

```python
from typing import Annotated, Literal
from pydantic import Field
from better_utils import BetterUtils, File, ImageFile, ToolError

app = BetterUtils(title="My Utils", tools_dir="tools")

@app.tool
def summarize(values: list[float]) -> dict:
    """Basic descriptive statistics for a list of numbers.

    Args:
        values: Numbers to summarize (JSON array in the UI).
    """
    return {"count": len(values), "average": sum(values) / len(values)}

@app.tool
def fib(members: Annotated[int, Field(ge=1, le=64)] = 10) -> list[int]:
    """First ``members`` Fibonacci numbers (the bound drives a UI slider)."""
    ...
```

Supported argument types:

| Annotation | UI control | Tool receives |
| --- | --- | --- |
| `str` | text input | `str` |
| `int` / `float` (+ `Field(ge/le)` bounds) | number input or slider | `int` / `float` |
| `bool` | checkbox | `bool` |
| `Literal[...]` / `Enum` | select | the native value |
| `list[T]` | JSON textarea | `list[T]` |
| `dict` | JSON textarea | `dict` |
| `File` | file input | raw `bytes` |
| `ImageFile` | file input | `PIL.Image.Image` |

Return anything JSON-serializable (rendered as JSON), a `str` (rendered as
text), or a `PIL.Image.Image` (rendered in the dashboard from an artifact
URL). Async tools work too — they run on the event loop instead of a worker
thread.

Raise `ToolError("clean message")` to abort with a user-facing error instead
of a traceback.

## Tool discovery

- `BetterUtils(tools_dir="tools")` scans a directory (recursively). Every
  `@tool` function is registered as `<file_stem>.<func_name>`; subfolders and
  file stems become sidebar groups.
- `BetterUtils` can also discover an importable package:
  `app.discover("mypkg.tools")`.
- `Router("text")` + `app.include_router(text)` registers functions defined
  anywhere as `text.<func_name>`. Passing `prefix=""` at include time drops
  the prefix.

Duplicate ids are an error — two sources claiming `text.reverse_string` fail
loudly instead of silently overwriting each other.

## Running

```
bu run module:attribute            # e.g. bu run app:app
bu run app:app --port 9000 --reload
bu --version
```

- `--reload` (or `BETTER_UTILS_RELOAD=1`) watches the tools directories:
  edits, additions, renames, and deletions hot-reload with a debounce; broken
  modules surface in the dashboard's error banner instead of crashing the
  server.
- Every `POST /api/run/<id>` executes the tool in a worker thread (never the
  event loop) with a hard timeout, so a slow tool cannot freeze the server.

## Testing tools

Put `tests/test_<file>.py` next to a tool file (or in `tools/tests/`) and use
the test button in the dashboard, or:

```
curl -X POST http://127.0.0.1:8000/api/test/text.reverse_string
```

Tests run in a pytest **subprocess** with a timeout — never inside the server
process. Statuses: `passed`, `failed`, `no_tests`, `error`.

## HTTP API

| Route | Purpose |
| --- | --- |
| `GET /api/tools` | `{tools: [...], errors: [...]}` — machine-readable catalog |
| `POST /api/run/{tool_id}` | JSON body (or multipart when the tool takes files) |
| `POST /api/test/{tool_id}` | run the tool's pytest subprocess |
| `GET /api/artifacts/{name}` | image artifacts returned by tools |
| `GET /health` | liveness + tool count |

Successful runs return `{"ok": true, "type": "json"|"text"|"image", "data": ...,
"image_url": ..., "elapsed_ms": ...}`. Errors: `404` `{"detail": ...}`,
`422` `{"ok": false, "error": ..., "validation": [{"name", "msg"}...]}`,
`400` (ToolError), `500` (with `traceback`), `504` (timeout) — all
`{"ok": false, "error": ...}` shaped.

## Interactive API docs

Every tool is also a **typed, documented endpoint** — the run table above is
the wire format, but you rarely need it. Point a browser at:

| URL | What it is |
| --- | --- |
| `/docs` | Swagger UI — per-tool forms with **Try it out** |
| `/redoc` | ReDoc — readable reference, grouped like the dashboard sidebar |
| `/openapi.json` | the spec itself, usable with any OpenAPI client generator |

Each tool gets its own `POST /api/run/<tool_id>` operation with a generated
request schema: argument types, defaults, enum choices, numeric and string
length bounds, descriptions from the docstring, and the response envelope.
Validation happens server-side against that same schema, so what the docs
show is exactly what the endpoint enforces. The `/docs` pages are generated
from the live registry — new tools appear after a hot reload.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `BETTER_UTILS_TOOLS_DIR` | — | directory auto-scanned at boot |
| `BETTER_UTILS_STATIC_DIR` | `better_utils/static` | dashboard assets (wheel-bundled) |
| `BETTER_UTILS_HOST` | `127.0.0.1` | bind address for `bu run` |
| `BETTER_UTILS_PORT` | `8000` | port for `bu run` |
| `BETTER_UTILS_TIMEOUT` | `60` | tool execution timeout (seconds) |
| `BETTER_UTILS_RELOAD` | `0` | file watcher on/off |
| `BETTER_UTILS_CORS_ORIGINS` | — | comma-separated allowed origins |
| `BETTER_UTILS_LOG_LEVEL` | `info` | uvicorn log level |

`BetterUtils(...)` keyword arguments and CLI flags override the environment.

## Development

```
git clone <repo> && cd better-utils
uv venv .venv && uv pip install -e '.[dev]'
.venv/bin/python -m pytest          # framework suite (tests/)
.venv/bin/ruff check .
./scripts/build_ui.sh               # build dashboard into better_utils/static
.venv/bin/bu run example_app:app    # example server with 9 tools
```

The frontend lives in `frontend/` (React + Vite + Tailwind) and is embedded
into `better_utils/static` by `scripts/build_ui.sh`; wheels built without it
serve a placeholder page.

## Docker

```
docker build -t better-utils .
docker run -p 8000:8000 better-utils
```

Multi-stage build: Node compiles the dashboard, Python builds the wheel with
it embedded, the runtime image installs the wheel and runs as non-root.

## Security warning

> **The tool runner executes arbitrary Python code.** Any Python file in the
> tools directory is imported and run by the server, with the permissions of
> the server process. There is no authentication, sandboxing, or resource
> limiting. Never expose Better Utils directly to the internet; run it on a
> trusted host and put authentication and network controls in front of it.
