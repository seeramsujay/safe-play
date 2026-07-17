# SafePlay - Workflow & Quality Gates

This document outlines team development standards, test requirements, and automated quality checks.

## Development Workflows

1. **Local Setup**:
   * Create a virtual environment using `uv venv`.
   * Install python dependencies: `uv pip install -r requirements.txt`.
   * Compile the Cython code: `uv run python setup.py build_ext --inplace`.
2. **Adding Dependencies**:
   * Add any new Python package to `requirements.txt` and run `uv pip install`.
   * Add any Node/JS tools using `pnpm`.
3. **Git Guidelines**:
   * Do not commit local environments or build folders (`.venv`, `build/`, `*.so`, `*.c`, `.pytest_cache`).
   * Verify all archives and local build objects are excluded in `.gitignore`.

## Quality & Testing Gates

*   **Test Execution**: Run tests before committing any changes:
    ```bash
    uv run pytest
    ```
*   **Test Coverage Targets**: Keep 100% pass rates for critical logic:
    - Custom Pydantic models & JSON schemas validation.
    - MQTT connection and subscription life cycle callbacks.
    - Copilot LLM & semantic fallbacks query matches.
    - Operator early approval and veto triggers.
*   **Cython Optimization Rule**: Any pathfinding routing alterations must be written in Cython (`src/routing.pyx`) and compiled for millisecond-latency SLA assurance.
*   **Async Integrity**: Ensure all ASGI endpoints and background tasks are fully non-blocking and use `asyncio.sleep` to allow task scheduling.
