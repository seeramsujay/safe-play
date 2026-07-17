"""
Domain-Specific Exceptions for SafePlay.

This module defines the custom exception hierarchy used throughout the orchestrator,
inference, and web API layers to ensure clear error boundaries and robust error handling.
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
