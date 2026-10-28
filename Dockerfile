# Stage 1: build the React dashboard
FROM node:22-alpine AS ui
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# Stage 2: build the wheel with the dashboard embedded
FROM python:3.12-slim AS wheel
WORKDIR /build
COPY better_utils/ better_utils/
COPY --from=ui /build/dist better_utils/static
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir build && python -m build -w -o dist

# Stage 3: runtime
FROM python:3.12-slim
RUN useradd --create-home --shell /usr/sbin/nologin bu
WORKDIR /app
COPY --from=wheel /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/better_utils-*.whl && rm /tmp/better_utils-*.whl
# The example app is a starting point; mount or bake your own project over /app.
COPY example_app.py /app/
COPY tools/ /app/tools/
USER bu
EXPOSE 8000
CMD ["bu", "run", "example_app:app", "--host", "0.0.0.0", "--port", "8000"]
