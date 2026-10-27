# Better Utils

Better Utils is a high-performance framework designed to instantly transform Python functions into interactive web user interfaces. By leveraging type hints and docstrings, it automatically generates type-safe, responsive forms, allowing developers to focus on logic rather than frontend boilerplate.

## Overview

This project bridges the gap between backend scripting and frontend usability. It parses Python function signatures to construct a dynamic registry of executable tools. A React-based frontend then renders these tools, offering a seamless experience for execution, testing, and hot-reloading.

## Security Warning

> **The tool runner executes arbitrary Python code.** Any Python file placed in the tools directory is imported and run by the server, with the same permissions as the server process. There is no authentication, sandboxing, or resource limiting. Never expose Better Utils directly to the internet or to an untrusted network; run it on a trusted host and put authentication and network controls in front of it.

## Key Features

- **Automatic UI Generation**: Instantly converts function signatures (including complex types) into web forms.
- **Dynamic Registry**: Automatically discovers and loads tools from the `tools/` directory.
- **Hot Reloading**: Integrated file watcher reloads modules instantly upon modification, accelerating the development loop.
- **Type Safety**: Built on standard Python type hints to ensure data integrity.
- **Testing Infrastructure**: Built-in test runner to validate tool logic directly from the UI.
- **Modern Stack**: Powered by FastAPI for high-performance backend serving and React/Vite for a responsive frontend experience.

## Technical Architecture

### Backend
- **Framework**: FastAPI (Python 3.9+)
- **Core Components**:
  - `Registry`: Manages tool discovery and lifecycle.
  - `Parser`: Analyzes AST and type hints to generate schemas.
  - `Executor`: Handles asynchronous execution and capturing of results.
  - `Watcher`: Uses `watchdog` to monitor filesystem changes.

### Frontend
- **Framework**: React with TypeScript and Vite.
- **Styling**: Modern CSS variables and responsive design principles.
- **State Management**: Real-time updates for execution status and logs.

## Configuration

Paths default to locations inside the project (or container image) and do not
depend on the process working directory. They can be overridden with
environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `BETTER_UTILS_TOOLS_DIR` | `<project>/tools` | Directory scanned for tool modules. |
| `BETTER_UTILS_STATIC_DIR` | `<project>/frontend/dist` | Built frontend assets. If missing, the API starts in API-only mode. |

## Getting Started

### Prerequisites
- Python 3.8 or higher
- Node.js 16+ (for frontend development)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/tanmayd-dev/better-utils
   cd better-utils
   ```

2. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Install frontend dependencies (optional for development):
   ```bash
   cd frontend
   npm install
   ```

### Usage

1. Build the frontend (optional; without it the API still runs, UI is disabled):
   ```bash
   cd frontend
   npm run build
   ```

2. Start the application:
   ```bash
   python main.py
   ```

3. Access the dashboard at `http://localhost:8000`. Health checks are available
   at `http://localhost:8000/health`.

4. Create a new tool by adding a Python script to the `tools/` directory:
   ```python
   # tools/text_utils.py

   def reverse_string(text: str) -> str:
       """
       Reverses the input text.
       """
       return text[::-1]
   ```
   The tool will automatically appear in the UI.

## Docker

The image builds the frontend in a Node stage and copies the artifacts into the
Python runtime, so it is self-contained and does not need the repository or a
build step on the host.

```bash
docker build -t better-utils .
docker run --rm -p 8000:8000 better-utils
```

With Podman, replace `docker` with `podman`. The container runs as a non-root
user and exposes port 8000. Remember the security warning above: publish the
port only on a trusted network.

## Development

- **Backend**: The `main.py` entry point serves the API, plus the static frontend when a build exists in `frontend/dist` (or `BETTER_UTILS_STATIC_DIR`).
- **Frontend**: Source code is located in `frontend/src`. Run `npm run dev` in the `frontend` directory for a standalone development server.
