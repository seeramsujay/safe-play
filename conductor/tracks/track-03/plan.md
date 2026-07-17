# Plan: Track-03 - Code Style Improvements & Hacker News Level Architecture

## Execution Checklist

### Phase 1: Define Domain Exceptions
- [ ] Create `src/exceptions.py` with:
  - `SafePlayError(Exception)`
  - `TelemetryValidationError(SafePlayError)`
  - `InferenceTimeoutError(SafePlayError)`
  - `GraphRoutingError(SafePlayError)`
  - `OperatorActionError(SafePlayError)`

### Phase 2: Refactor Models & Graph Initialization
- [ ] Extract the default World Cup 2026 stadium `SpatialGraph` configuration from `src/orchestrator.py` into a static factory method `get_default_world_cup_graph()` in `src/models.py`.
- [ ] Refactor `src/orchestrator.py` constructor to initialize using the factory method.

### Phase 3: Enhance Orchestrator Logic & Error Handling
- [ ] Update `src/orchestrator.py` to import and utilize custom exceptions.
- [ ] Add explicit typing and expand docstrings on public methods.
- [ ] Refactor async telemetry queue parsing to raise `TelemetryValidationError` on corrupted JSON or invalid fields, ensuring it fails gracefully and falls back to safe rules.

### Phase 4: Polish API, Copilot & Inference Modules
- [ ] Refactor `src/web_api.py` to use custom exceptions and return appropriate HTTP status codes (e.g. 400 for validation errors, 404 for missing resources).
- [ ] Review `src/copilot.py` and `src/inference.py` to check type annotations and formatting.

### Phase 5: Repository Hygiene
- [ ] Review `.gitignore` to ensure `.venv`, `build/`, `*.so`, `*.c`, `.pytest_cache`, and other local artifacts are fully excluded.
- [ ] Run the compilation and unit test suite to verify zero regressions.
