"""Application configuration.

Paths are resolved from this file's location (the project/container root) by
default instead of the process working directory, so the app starts the same
way no matter where it is launched from. Every path can be overridden with an
environment variable for deployments that keep data outside the image.
"""

import os
from pathlib import Path


def _env_path(name: str, default: Path) -> Path:
    """Return the path from ``name`` if it is set, otherwise ``default``."""
    value = os.environ.get(name)
    if not value:
        return default
    return Path(value).expanduser().resolve()


PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Directory scanned for tool modules.
TOOLS_DIR = _env_path("BETTER_UTILS_TOOLS_DIR", PROJECT_ROOT / "tools")

# Built frontend assets served at "/". Optional: the API runs without it.
STATIC_DIR = _env_path("BETTER_UTILS_STATIC_DIR", PROJECT_ROOT / "frontend" / "dist")
