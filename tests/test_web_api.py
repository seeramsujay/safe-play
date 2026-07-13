import pytest
from fastapi.testclient import TestClient
from src.orchestrator import SafePlayOrchestrator, create_app
from src.models import TelemetryPayload, InterventionScript
import json
import asyncio

def test_api_config():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    # Test GET /api/config
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "actuation_sla_sec" in data
    assert "fallback_density_limit" in data
    
    # Test POST /api/config
    response = client.post("/api/config", json={"actuation_sla_sec": 3.0, "fallback_density_limit": 4.0})
    assert response.status_code == 200
    data = response.json()
    assert data["actuation_sla_sec"] == 3.0
    assert data["fallback_density_limit"] == 4.0

def test_api_audit_logs():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    response = client.get("/api/audit-logs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_api_telemetry():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 1.2,
        "flow_rate_in": 20.0,
        "flow_rate_out": 15.0,
        "timestamp": 1720875600.0
    }
    response = client.post("/api/telemetry", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

def test_websocket_connection():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "state_update"
        assert "nodes" in data
        assert "edges" in data
        assert "system_health" in data

@pytest.mark.anyio
async def test_operator_veto_action():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    # 1. Trigger elevated density telemetry to start an active intervention script
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 5.0,
        "flow_rate_in": 80.0,
        "flow_rate_out": 20.0,
        "timestamp": 1720875600.0
    }
    await orchestrator.process_telemetry(json.dumps(payload))
    await asyncio.sleep(0.01)  # Yield loop to allow run_intervention_lifecycle task to schedule
    
    # 2. Assert intervention script is generated & stored in orchestrator state
    assert "Gate_A" in orchestrator.active_scripts
    
    # 3. Trigger operator veto
    response = client.post("/api/veto", json={"zone_id": "Gate_A"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    await asyncio.sleep(0.01)  # Yield loop to allow task cancellation logic to complete
    
    # 4. Verify zone was recorded as vetoed and popped out of active scripts
    assert "Gate_A" in orchestrator.vetoed_zones
    assert "Gate_A" not in orchestrator.active_scripts

@pytest.mark.anyio
async def test_operator_approve_action():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    # 1. Trigger elevated telemetry
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 5.0,
        "flow_rate_in": 80.0,
        "flow_rate_out": 20.0,
        "timestamp": 1720875600.0
    }
    await orchestrator.process_telemetry(json.dumps(payload))
    await asyncio.sleep(0.01)  # Yield loop to allow task to schedule
    
    # 2. Trigger early approval
    response = client.post("/api/approve", json={"zone_id": "Gate_A"})
    assert response.status_code == 200
    assert response.json()["status"] == "success"
    await asyncio.sleep(0.01)  # Yield loop to allow approval completion logic to finish
    
    # 3. Verify popped out of active scripts
    assert "Gate_A" not in orchestrator.active_scripts

@pytest.mark.anyio
async def test_dynamic_qos_escalation_lifecycle():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    
    # 1. Check initial QoS default (0)
    assert orchestrator.zone_qos.get("Gate_A", 0) == 0
    
    # 2. Ingest low density telemetry (no escalation)
    raw_payload_low = '{"zone_id": "Gate_A", "crowd_density": 1.2, "flow_rate_in": 20.0, "flow_rate_out": 15.0, "timestamp": 1720875600.0}'
    await orchestrator.process_telemetry(raw_payload_low)
    assert orchestrator.zone_qos.get("Gate_A", 0) == 0
    
    # 3. Ingest high density telemetry (triggers QoS escalation to 1)
    raw_payload_high = '{"zone_id": "Gate_A", "crowd_density": 2.5, "flow_rate_in": 80.0, "flow_rate_out": 20.0, "timestamp": 1720875600.0}'
    await orchestrator.process_telemetry(raw_payload_high)
    assert orchestrator.zone_qos.get("Gate_A", 0) == 1
    
    # 4. Ingest low density telemetry again (de-escalates back to 0)
    await orchestrator.process_telemetry(raw_payload_low)
    assert orchestrator.zone_qos.get("Gate_A", 0) == 0

def test_signature_verification_stub():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    assert orchestrator.verify_payload_signature(None) is False
    assert orchestrator.verify_payload_signature("") is False
    assert orchestrator.verify_payload_signature("valid_looking_raw_string") is True

@pytest.mark.anyio
async def test_api_panic_mode():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    app = create_app(orchestrator)
    client = TestClient(app)
    
    # 1. Trigger elevated density telemetry to start an active intervention
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 5.0,
        "flow_rate_in": 80.0,
        "flow_rate_out": 20.0,
        "timestamp": 1720875600.0
    }
    await orchestrator.process_telemetry(json.dumps(payload))
    await asyncio.sleep(0.01)
    assert "Gate_A" in orchestrator.active_scripts
    
    # 2. Activate panic mode
    response = client.post("/api/panic")
    assert response.status_code == 200
    assert response.json()["panic_mode"] is True
    assert orchestrator.panic_mode is True
    
    # 3. Verify active intervention was cancelled/cleared
    await asyncio.sleep(0.01)
    assert "Gate_A" not in orchestrator.active_scripts
    
    # 4. Check that new telemetry is ignored during panic mode
    await orchestrator.process_telemetry(json.dumps(payload))
    await asyncio.sleep(0.01)
    assert "Gate_A" not in orchestrator.active_scripts
    
    # 5. Clear panic mode
    response = client.post("/api/panic/clear")
    assert response.status_code == 200
    assert response.json()["panic_mode"] is False
    assert orchestrator.panic_mode is False


