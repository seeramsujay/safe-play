# SafePlay - Technical Stack Specification

This document defines the technology stack, dependencies, compiler options, and environment setups.

## Core Stack

*   **Backend Orchestrator**: Python 3.12 (Asynchronous runtime via `asyncio`).
*   **Web API Framework**: FastAPI (Uvicorn ASGI web server).
*   **Performance Core**: Cython (C-compiled extensions for high-speed pathfinding).
*   **IoT Messaging Gateway**: MQTT (Paho-MQTT client for sensor telemetry).
*   **Operator Dashboard**: HTML5, Vanilla CSS3, WebSockets for real-time updates.

## Python Dependency Management (`uv`)

We manage Python dependencies and virtual environments exclusively using `uv` for local setup.
*   **Virtualenv Folder**: Located at `.venv`.
*   **Dependency Resolution**: Run `uv pip install -r requirements.txt`.
*   **Python Project Configuration**: Managed in `pyproject.toml`.

## Node.js Dependency Management (`pnpm`)

All frontend, static site generation, or Node.js packages must be managed using `pnpm`.
*   Do not use npm or yarn.

## Key Libraries & Versions

*   `fastapi`: Lightweight ASGI web framework.
*   `uvicorn`: Performance-oriented ASGI web server implementation.
*   `paho-mqtt`: MQTT communication protocols.
*   `pydantic`: Data validation and schema enforcement.
*   `httpx`: Asynchronous HTTP client for LLM API calls.
*   `pytest` & `anyio`: Comprehensive test suites.

## Compilation Target

*   Cython pathfinding compilation runs via `setup.py`:
    ```bash
    uv run python setup.py build_ext --inplace
    ```
*   Compiles `src/routing.pyx` to a shared C binary (`src/routing.cpython-*.so`).
*   Requires a native C compiler (`gcc` or `clang`).
