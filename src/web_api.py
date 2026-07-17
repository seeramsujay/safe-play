"""
Web API Layer for the SafePlay Crowd Safety Orchestrator.

This module exposes the REST endpoints and WebSockets routing needed for real-time 
dashboard telemetry ingestion, operator command override (veto/approve), 
live audit trails, and configuration updates.
"""

import os
import json
import time
from typing import Optional
from collections import deque
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from src.config import AUDIT_LOG_FILE, logger

# ---------------------------------------------------------------------------
# Pydantic request models — validate API inputs instead of accepting raw dicts
# ---------------------------------------------------------------------------

class ZoneActionRequest(BaseModel):
    """Schema representing an operator action target zone (e.g. for vetos or approvals)."""
    zone_id: str = Field(
        ..., 
        min_length=1, 
        max_length=64, 
        description="The target zone identifier where the action is executed"
    )

class TelemetryRequest(BaseModel):
    """Schema representing raw incoming telemetry data from edge ingestion devices."""
    zone_id: str = Field(
        ..., 
        min_length=1, 
        max_length=64, 
        description="Target vomitory or quadrant zone ID"
    )
    crowd_density: float = Field(
        ..., 
        ge=0.0, 
        le=20.0, 
        description="Recorded crowd density in people per square meter"
    )
    flow_rate_in: float = Field(
        ..., 
        ge=0.0, 
        description="Inflow rate of people per minute"
    )
    flow_rate_out: float = Field(
        ..., 
        ge=0.0, 
        description="Outflow rate of people per minute"
    )
    timestamp: float = Field(
        ..., 
        gt=0.0, 
        description="Inflow timestamp"
    )

class ConfigUpdateRequest(BaseModel):
    """Schema for updating the dynamic orchestration limits and SLA parameters."""
    actuation_sla_sec: Optional[float] = Field(
        None, 
        ge=2.0, 
        le=300.0, 
        description="Dynamic countdown timer window (in seconds) during which operators can veto recommendations"
    )
    fallback_density_limit: Optional[float] = Field(
        None, 
        ge=0.5, 
        le=10.0, 
        description="Safe threshold density at which automatic backup policies execute"
    )

def create_app(orchestrator) -> FastAPI:
    """
    Factory function creating and configuring the FastAPI application instance.
    Injects the active orchestrator context to wire routes to domain models.
    
    Args:
        orchestrator: The main system Orchestrator instance.
        
    Returns:
        A configured FastAPI application.
    """
    app = FastAPI(
        title="EdgePulse 2026 - Smart Campus Crowd Safety & Egress Orchestrator",
        description="Real-time crowd safety orchestration and incident egress routing for smart campus events.",
        version="0.1.0",
    )

    # Establish filepath to local static directory containing frontend assets
    current_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(current_dir, "static")

    @app.get("/", response_class=HTMLResponse)
    async def get_index():
        """Serves the primary EdgePulse 2026 Operator Dashboard HTML webpage."""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                return HTMLResponse(content=f.read(), status_code=200)
        return HTMLResponse(content="<h1>static/index.html not found!</h1>", status_code=404)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket connection handler for live real-time dashboard telemetry updates.
        Registers the incoming socket with the connection manager and keeps the channel alive.
        """
        await orchestrator.manager.connect(websocket)
        try:
            # Broadcast the initial state model immediately upon successful registration
            await orchestrator.broadcast_state()
            while True:
                # Listen for incoming client keep-alives (pings) to prevent connection timeouts
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            # Guarantee clean deregistration from client collection upon disconnect
            orchestrator.manager.disconnect(websocket)

    @app.post("/api/veto")
    async def post_veto(payload: ZoneActionRequest):
        """Allows operators to veto/cancel a proposed safety gate intervention."""
        await orchestrator.reject_intervention_veto(payload.zone_id)
        return {"status": "success", "zone_id": payload.zone_id}

    @app.post("/api/approve")
    async def post_approve(payload: ZoneActionRequest):
        """Allows operators to early-approve a proposed intervention, bypassing the SLA window."""
        await orchestrator.approve_intervention_early(payload.zone_id)
        return {"status": "success", "zone_id": payload.zone_id}

    @app.post("/api/panic")
    async def post_panic():
        """Puts the orchestrator immediately into global system panic mode (emergency exit gates fully opened)."""
        await orchestrator.trigger_panic_mode()
        return {"status": "success", "panic_mode": True}

    @app.post("/api/panic/clear")
    async def post_panic_clear():
        """Restores the orchestrator to normal monitoring state from system panic mode."""
        await orchestrator.clear_panic_mode()
        return {"status": "success", "panic_mode": False}

    @app.post("/api/telemetry")
    async def post_telemetry(payload: TelemetryRequest):
        """
        Accepts sensor telemetry payloads over HTTP. Ingests the data into the main
        processing queue and updates the manual input timestamp.
        """
        orchestrator.last_manual_telemetry_time = time.time()
        orchestrator.telemetry_queue.put_nowait(payload.model_dump_json())
        return {"status": "success", "message": "Telemetry queued"}

    @app.get("/api/audit-logs")
    async def get_audit_logs(limit: int = 100):
        """
        Returns the last `limit` audit trail logs (maximum capped at 500 records).
        Uses a double-ended queue (deque) with maxlen constraint for O(N) linear parsing
        efficiency and memory safety under high logging loads.
        """
        limit = min(max(limit, 1), 500)
        logs: deque = deque(maxlen=500)
        
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        try:
                            logs.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            # Silently ignore malformed/corrupted file records
                            pass
        
        # Convert deque collection to standard list and slice last limit entries
        return list(logs)[-limit:]

    @app.get("/api/config")
    async def get_config():
        """Exposes dynamic orchestrator settings and broker endpoints."""
        return {
            "actuation_sla_sec": orchestrator.actuation_sla_sec,
            "fallback_density_limit": orchestrator.fallback_density_limit,
            "broker": orchestrator.broker,
            "port": orchestrator.port,
        }

    @app.post("/api/config")
    async def post_config(payload: ConfigUpdateRequest):
        """
        Updates dynamic runtime system settings on the current orchestrator instance.
        Triggers an immediate WebSocket state broadcast to update UI configuration indicators.
        """
        if payload.actuation_sla_sec is not None:
            orchestrator.actuation_sla_sec = payload.actuation_sla_sec
        if payload.fallback_density_limit is not None:
            orchestrator.fallback_density_limit = payload.fallback_density_limit
            
        await orchestrator.broadcast_state()
        return {
            "status": "success",
            "actuation_sla_sec": orchestrator.actuation_sla_sec,
            "fallback_density_limit": orchestrator.fallback_density_limit,
        }

    return app
