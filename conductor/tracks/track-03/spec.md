# Specification: Track-03 - Code Style Improvements & Hacker News Level Architecture

## Goal
Elevate the SafePlay codebase to "Hacker News level" engineering quality. This means writing code that is exceptionally elegant, simple, type-safe, performant, and defensive.

## Requirements

### 1. Unified Domain Exceptions
*   Introduce structured custom domain exceptions in a dedicated module `src/exceptions.py` (e.g., `SafePlayError`, `TelemetryValidationError`, `InferenceTimeoutError`, `GraphRoutingError`).
*   Ensure the orchestrator, inference, and Web API handle exceptions gracefully using these structured domain errors.

### 2. Clean Constructor & Spatial Graph Setup
*   Move the hardcoded SpatialGraph definition out of `SafePlayOrchestrator.__init__` and into a factory method in `src/models.py`. Keep the orchestrator constructor clean and focused on resource initialization.

### 3. Strict Typing & Docstrings
*   Double check that all methods in `src/orchestrator.py`, `src/web_api.py`, `src/copilot.py`, and `src/inference.py` have full type signatures.
*   Enforce descriptive Google/NumPy style docstrings explaining the mathematical/logical rationale of components rather than just repeating the code statement.

### 4. Git Hygiene & Repository Structure
*   Update `.gitignore` to guarantee local build systems (Cython `.so`, `.c`, `build/`), virtual environments (`.venv`), caching structures (`.pytest_cache`), and temporary files are fully ignored.

## Acceptance Criteria
- [ ] No generic `except Exception:` blocks without logging and/or re-raising, unless explicitly needed for bulletproof fallbacks.
- [ ] Pytest suite continues to report 100% pass rates (all 44 tests pass).
- [ ] Clean type checks throughout the project.
- [ ] Clear file separation with no redundant code or hardcoded configs.
