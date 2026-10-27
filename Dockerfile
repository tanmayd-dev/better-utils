# syntax=docker/dockerfile:1

# ---- Frontend build ----
FROM node:22-alpine AS frontend-build

WORKDIR /app/frontend

# The repository uses bun.lock; install with npm from package.json so the build
# only needs the Node 22 toolchain.
COPY frontend/package.json ./
RUN npm install --no-audit --no-fund

COPY frontend/ ./
RUN npm run build

# ---- Runtime ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BETTER_UTILS_TOOLS_DIR=/app/tools \
    BETTER_UTILS_STATIC_DIR=/app/frontend/dist

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=appuser:appuser main.py ./
COPY --chown=appuser:appuser core ./core
COPY --chown=appuser:appuser tools ./tools
COPY --chown=appuser:appuser --from=frontend-build /app/frontend/dist ./frontend/dist

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"]

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
