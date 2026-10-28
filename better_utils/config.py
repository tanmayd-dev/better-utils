"""Runtime settings: environment variables first, BetterUtils(...) kwargs win.

| Variable                  | Default                    | Purpose                        |
| ------------------------- | -------------------------- | ------------------------------ |
| BETTER_UTILS_TOOLS_DIR    | (none)                     | directory auto-scanned at boot |
| BETTER_UTILS_STATIC_DIR   | ``better_utils/static``    | bundled dashboard assets       |
| BETTER_UTILS_HOST         | ``127.0.0.1``              | bind address for ``bu run``    |
| BETTER_UTILS_PORT         | ``8000``                   | port for ``bu run``            |
| BETTER_UTILS_TIMEOUT      | ``60``                     | tool execution timeout (s)     |
| BETTER_UTILS_RELOAD       | ``0``                      | file watcher on/off            |
| BETTER_UTILS_CORS_ORIGINS | (none)                     | comma separated origins        |
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Settings"]

logger = logging.getLogger("better_utils.config")

PACKAGE_DIR = Path(__file__).resolve().parent


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name)
    if not value:
        return None
    return Path(value).expanduser().resolve()


@dataclass
class Settings:
    host: str = "127.0.0.1"
    port: int = 8000
    timeout_s: float = 60.0
    reload: bool = False
    log_level: str = "info"
    cors_origins: list[str] | None = None
    tools_dir: Path | None = None
    static_dir: Path = field(default_factory=lambda: PACKAGE_DIR / "static")
    test_timeout_s: float = 60.0

    @classmethod
    def from_env(cls) -> Settings:
        cors = os.environ.get("BETTER_UTILS_CORS_ORIGINS")
        return cls(
            host=os.environ.get("BETTER_UTILS_HOST", "127.0.0.1"),
            port=_int_env("BETTER_UTILS_PORT", 8000),
            timeout_s=_float_env("BETTER_UTILS_TIMEOUT", 60.0),
            reload=_bool_env("BETTER_UTILS_RELOAD", False),
            log_level=os.environ.get("BETTER_UTILS_LOG_LEVEL", "info"),
            cors_origins=[o.strip() for o in cors.split(",") if o.strip()] if cors else None,
            tools_dir=_env_path("BETTER_UTILS_TOOLS_DIR"),
            static_dir=_env_path("BETTER_UTILS_STATIC_DIR") or (PACKAGE_DIR / "static"),
        )

    def with_overrides(self, **kwargs) -> Settings:
        """Return a copy with non-None kwargs applied (None = keep default)."""
        from dataclasses import fields as dc_fields

        current = {f.name: getattr(self, f.name) for f in dc_fields(self)}
        merged = {**current, **{k: v for k, v in kwargs.items() if v is not None}}
        return Settings(**merged)


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        logger.warning("invalid %s=%r, using %s", name, os.environ.get(name), default)
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        logger.warning("invalid %s=%r, using %s", name, os.environ.get(name), default)
        return default


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def resolve_static_dir(settings_value: Path) -> Path | None:
    """The static dir only counts when it actually exists (API-only fallback)."""
    candidate = _env_path("BETTER_UTILS_STATIC_DIR") or settings_value
    if candidate is not None and candidate.is_dir() and any(candidate.iterdir()):
        return candidate
    return None
