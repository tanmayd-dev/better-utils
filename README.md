# Better Utils

Better Utils is a high-performance framework designed to instantly transform Python functions into interactive web user interfaces. By leveraging type hints and docstrings, it automatically generates type-safe, responsive forms, allowing developers to focus on logic rather than frontend boilerplate.

## Overview

This project bridges the gap between backend scripting and frontend usability. It parses Python function signatures to construct a dynamic registry of executable tools. A React-based frontend then renders these tools, offering a seamless experience for execution, testing, and hot-reloading.

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

## Getting Started

### Prerequisites
- Python 3.8 or higher
- Node.js 16+ (for frontend development)

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/tanmaydeshpande/better-utils.git
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

1. Start the application:
   ```bash
   python main.py
   ```

2. Access the dashboard at `http://localhost:8000`.

3. Create a new tool by adding a Python script to the `tools/` directory:
   ```python
   # tools/text_utils.py

   def reverse_string(text: str) -> str:
       """
       Reverses the input text.
       """
       return text[::-1]
   ```
   The tool will automatically appear in the UI.

## Development

- **Backend**: The `main.py` entry point serves both the API and the static frontend assets.
- **Frontend**: Source code is located in `frontend/src`. Run `npm run dev` in the `frontend` directory for a standalone development server.

## License

Copyright (c) 2024 Tanmay Deshpande. All rights reserved.
