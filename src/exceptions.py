"""
Domain-Specific Exceptions for SafePlay.

Role:
    Defines the custom exception hierarchy used throughout the SafePlay platform
    to enforce clear error boundaries, standardise logging, and map runtime failures
    to appropriate API response codes.

Ecosystem Positioning:
    - Below: Built-in Python Exception class.
    - Above: Used by `src/models.py` (during graph parsing), `src/inference.py` (when SLM query
      timeouts/errors occur), `src/orchestrator.py` (when parsing incoming telemetry or handling
      veto timeouts), and `src/web_api.py` (translating internal exceptions like
      OperatorActionError to specific FastAPI HTTP status codes like 400 Bad Request).
"""


class SafePlayError(Exception):
    """Base exception class for all SafePlay orchestration errors."""
    pass

class TelemetryValidationError(SafePlayError):
    """Raised when incoming telemetry data is malformed or violates schema constraints."""
    pass

class InferenceTimeoutError(SafePlayError):
    """Raised when the LLM/SLM inference engine fails to respond within the SLA window."""
    pass

class GraphRoutingError(SafePlayError):
    """Raised when spatial graph routing calculations detect partition errors or invalid edges."""
    pass

class OperatorActionError(SafePlayError):
    """Raised when an invalid operator veto or approval action is executed."""
    pass
