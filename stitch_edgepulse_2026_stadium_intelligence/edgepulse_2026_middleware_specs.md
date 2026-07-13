# EdgePulse 2026: Edge-Intelligence Middleware for Stadium Crowd Safety

This service acts as the orchestrator between edge sensors (MQTT), local LLM inference servers (llama.cpp), and the VOC Command Dashboard.

## Architecture Overview
- **Orchestrator**: Async Python (`asyncio`) managing the message lifecycle.
- **Inference**: Connects to `llama-server` instances using GBNF grammars for structured JSON output.
- **Validation**: Pydantic v2 ensures all model outputs conform to `StadiumSecurityIncidentReport`.
- **Reliability**:
    - **QoS Escalation**: Auto-upgrades MQTT QoS 0 to QoS 1 for flagged hazard grids.
    - **Degraded Mode**: Fallback to rule-based logic if LLM servers are unreachable.
    - **Human-in-the-Loop**: Actuation commands require operator approval via the dashboard.

## File Structure
- `middleware/`: Main service logic.
- `schemas/`: Pydantic models.
- `tests/`: Validation and fallback path tests.
- `config/`: MQTT and TLS stubs.

---

### Python Middleware Implementation (Partial)

```python
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict
from pydantic import BaseModel, Field, validator

# --- Schemas ---

class StadiumSecurityIncidentReport(BaseModel):
    incident_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    zone: int = Field(..., ge=1, le=3)
    node_id: str
    incident_type: str  # e.g., "CROWD_CRUSH", "UNAUTHORIZED_ENTRY"
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    confidence: float = Field(..., ge=0.0, le=1.0)
    suggested_action: Optional[str] = None
    requires_human_approval: bool = False
    raw_telemetry_snapshot: Dict

# --- Middleware Core ---

class EdgePulseOrchestrator:
    def __init__(self, mqtt_client, llm_url: str):
        self.mqtt = mqtt_client
        self.llm_url = llm_url
        self.degraded_mode = False

    async def handle_sensor_data(self, topic: str, payload: bytes):
        data = json.loads(payload)
        node_id = data.get("node_id")
        density = data.get("density", 0.0)

        # Degraded Mode Check
        if self.degraded_mode:
            return await self.fallback_logic(node_id, density)

        try:
            # LLM Inference with GBNF constraint
            report = await self.infer_incident(data)
            await self.process_report(report)
        except Exception as e:
            logging.error(f"LLM Failure: {e}. Falling back.")
            await self.fallback_logic(node_id, density)

    async def fallback_logic(self, node_id: str, density: float):
        if density > 3.0:
            msg = f"CRITICAL: Density {density} at {node_id}. Triggering static signage."
            await self.mqtt.publish("stadium/actuators/signage", msg, qos=1)
```
