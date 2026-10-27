import logging
import os
import sys
from pathlib import Path

# Make `core` importable regardless of the process working directory.
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import uvicorn
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response

from core.config import STATIC_DIR, TOOLS_DIR
from core.registry import ToolRegistry
from core.executor import execute_tool
from core.watcher import start_watcher
from core.tester import run_tests_for_tool

logger = logging.getLogger("better_utils")

app = FastAPI(title="Better Utils")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registry
registry = ToolRegistry(str(TOOLS_DIR))
registry.load_tools()

# Watcher
start_watcher(registry, str(TOOLS_DIR))

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/tools")
def list_tools():
    return registry.get_tools_list()

@app.post("/api/run/{tool_id}")
async def run_tool(tool_id: str, request: Request):
    tool_def = registry.get_tool(tool_id)
    if not tool_def:
        return {"error": "Tool not found"}
    
    # Parse form data
    form = await request.form()
    args = {}
    for key, value in form.items():
        args[key] = value
        
    try:
        result = await execute_tool(tool_def, args)
        if result["type"] == "image":
            return Response(content=result["data"], media_type=result["mime"])
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/test/{tool_id}")
def test_tool(tool_id: str):
    tool_def = registry.get_tool(tool_id)
    if not tool_def:
        return {"error": "Tool not found"}
        
    return run_tests_for_tool(tool_def["path"])

# Serve Frontend (mounted last so API routes take precedence).
# The build is an optional artifact: a missing frontend/dist must not prevent
# the API from starting.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:
    logger.warning(
        "Static frontend directory %s does not exist; serving API only. "
        "Build it with `npm run build` in frontend/ or set "
        "BETTER_UTILS_STATIC_DIR.",
        STATIC_DIR,
    )

if __name__ == "__main__":
    # Redirect stdout/stderr to a log file if running without a console (e.g. via pythonw)
    if sys.stdout is None or sys.stderr is None:
        log_path = os.path.join(os.getcwd(), "app.log")
        # Use line buffering (buffering=1) so logs appear immediately
        sys.stdout = open(log_path, "a", buffering=1)
        sys.stderr = open(log_path, "a", buffering=1)

    uvicorn.run(app, host="0.0.0.0", port=8000)
