import pytest
from fastapi.testclient import TestClient
from src.orchestrator import SafePlayOrchestrator, create_app
from src.models import TelemetryPayload, InterventionScript
import json

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
