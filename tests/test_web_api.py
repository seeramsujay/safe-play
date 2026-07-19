"""
Unit and integration tests for the SafePlay FastAPI Web API layer.

Role:
    Exercises all HTTP REST routes and WebSocket flows, including config retrieval,
    telemetry POST ingestion, operator veto/approval endpoints, copilot interaction,
    and cryptographic audit ledger checks.

Ecosystem Positioning:
    - Below: pytest test library and FastAPI TestClient.
    - Above: Validates request validation, route handling, and exceptions mapped
      inside `src/web_api.py`, translating actions down to `src/orchestrator.py`.
"""

import pytest
from fastapi.testclient import TestClient
from src.orchestrator import SafePlayOrchestrator, create_app
import json
import asyncio

@pytest.fixture
def orchestrator():
    """Fixture to provide a clean SafePlayOrchestrator instance for each test."""
    return SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)

@pytest.fixture
def app(orchestrator):
    """Fixture to provide the FastAPI application instance."""
    return create_app(orchestrator)

@pytest.fixture
def client(app):
    """Fixture to provide a TestClient instance for calling endpoints."""
    with TestClient(app) as client:
        yield client

def test_api_config(client):
    """Verifies retrieval and update of the orchestrator configuration parameters."""
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

def test_api_audit_logs(client):
    """Verifies that audit trail log lists are accessible via the API."""
    response = client.get("/api/audit-logs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_api_telemetry(client):
    """Tests successful telemetry submission through the REST endpoint."""
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

def test_websocket_connection(client):
    """Validates real-time state synchronization via WebSocket broadcast."""
    with client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "state_update"
        assert "nodes" in data
        assert "edges" in data
        assert "system_health" in data

@pytest.mark.anyio
async def test_operator_veto_action(orchestrator, client):
    """Verifies that an operator veto cancels a proposed safety gate intervention."""
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
async def test_operator_approve_action(orchestrator, client):
    """Ensures that early approval bypasses the veto SLA window and completes intervention."""
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
async def test_dynamic_qos_escalation_lifecycle(orchestrator):
    """Validates MQTT QoS auto-escalation/de-escalation based on zone density thresholds."""
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

def test_signature_verification_stub(orchestrator):
    """Tests the verification method for telemetry payload signatures."""
    # Test invalid inputs
    assert orchestrator.verify_payload_signature(None) is False
    assert orchestrator.verify_payload_signature("") is False
    
    # Test valid signed payload
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 1.2,
        "flow_rate_in": 20.0,
        "flow_rate_out": 15.0,
        "timestamp": 1720875600.0
    }
    import hmac
    import hashlib
    import json
    import os
    
    serialized = json.dumps(payload, sort_keys=True)
    secret = os.environ.get("TELEMETRY_SECRET_KEY", "safe-play-telemetry-secret-key-2026").encode("utf-8")
    sig = hmac.new(secret, serialized.encode("utf-8"), hashlib.sha256).hexdigest()
    
    payload_signed = dict(payload)
    payload_signed["signature"] = sig
    
    # Enable strict mode for the test
    orchestrator.strict_signature_verification = True
    try:
        # Verify valid signature passes
        assert orchestrator.verify_payload_signature(json.dumps(payload_signed)) is True
        
        # Verify unsigned payload fails in strict mode
        assert orchestrator.verify_payload_signature(json.dumps(payload)) is False
        
        # Verify tampered signature fails
        payload_signed_tampered = dict(payload_signed)
        payload_signed_tampered["signature"] = "invalid_signature"
        assert orchestrator.verify_payload_signature(json.dumps(payload_signed_tampered)) is False
    finally:
        orchestrator.strict_signature_verification = False

@pytest.mark.anyio
async def test_api_panic_mode(orchestrator, client):
    """Tests triggering and clearing of the system-wide emergency panic mode."""
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

@pytest.mark.anyio
async def test_dynamic_qos_subscription_calls(orchestrator):
    """Tests that MQTT subscriptions are updated automatically when QoS changes."""
    from unittest.mock import MagicMock
    mock_mqtt_client = MagicMock()
    orchestrator.mqtt_client = mock_mqtt_client
    
    # 1. Low density: no subscription calls should occur
    payload_low = {
        "zone_id": "Gate_A",
        "crowd_density": 1.2,
        "flow_rate_in": 20.0,
        "flow_rate_out": 15.0,
        "timestamp": 1720875600.0
    }
    await orchestrator.process_telemetry(json.dumps(payload_low))
    mock_mqtt_client.subscribe.assert_not_called()
    
    # 2. High density: should subscribe to Gate_A topic at QoS 1
    payload_high = {
        "zone_id": "Gate_A",
        "crowd_density": 2.5,
        "flow_rate_in": 80.0,
        "flow_rate_out": 20.0,
        "timestamp": 1720875600.0
    }
    await orchestrator.process_telemetry(json.dumps(payload_high))
    mock_mqtt_client.subscribe.assert_called_once_with("stadium/Gate_A/telemetry", qos=1)
    mock_mqtt_client.subscribe.reset_mock()
    
    # 3. Low density again: should unsubscribe from Gate_A topic
    await orchestrator.process_telemetry(json.dumps(payload_low))
    mock_mqtt_client.unsubscribe.assert_called_once_with("stadium/Gate_A/telemetry")

def test_api_veto_invalid_zone(client):
    """Validates that empty/invalid veto payloads are rejected with 422 errors."""
    response = client.post("/api/veto", json={})
    assert response.status_code == 422
    assert any("zone_id" in str(e) for e in response.json()["detail"])

def test_api_approve_invalid_zone(client):
    """Validates that empty/invalid early approval payloads are rejected with 422 errors."""
    response = client.post("/api/approve", json={})
    assert response.status_code == 422
    assert any("zone_id" in str(e) for e in response.json()["detail"])

def test_api_telemetry_malformed(client):
    """Tests that missing mandatory parameters in telemetry are rejected with 422 errors."""
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 1.2,
        "flow_rate_in": 20.0,
        "flow_rate_out": 15.0
    }
    response = client.post("/api/telemetry", json=payload)
    assert response.status_code == 422
    assert any("timestamp" in str(e) for e in response.json()["detail"])

def test_api_config_invalid_data(client):
    """Verifies validation boundaries for configuration updates."""
    # Non-numeric actuation_sla_sec
    response = client.post("/api/config", json={"actuation_sla_sec": "not-a-number"})
    assert response.status_code == 422
    
    # Out-of-bounds actuation_sla_sec
    response = client.post("/api/config", json={"actuation_sla_sec": 0.5})
    assert response.status_code == 422

def test_api_copilot(client):
    """Tests interaction with the GenAI-powered Stadium operations copilot endpoint."""
    # 1. Ask a question about status using standard 'prompt'
    response = client.post("/api/copilot", json={"prompt": "Is the system healthy?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "response" in data
    assert data["answer"] == data["response"]
    assert "source" in data
    assert len(data["answer"]) > 0
    assert "hazard_summary" in data
    assert "active_incident_count" in data

    # Test compatibility with 'query' key in request payload
    response_query = client.post("/api/copilot", json={"query": "Is the system healthy?"})
    assert response_query.status_code == 200
    data_query = response_query.json()
    assert data_query["answer"] == data_query["response"]
    assert data_query["source"] in ("gemini", "fallback")

    # 2. Empty prompt
    response = client.post("/api/copilot", json={"prompt": ""})
    assert response.status_code == 422

    # 3. Accessibility query
    response = client.post("/api/copilot", json={"prompt": "Where is the wheelchair ramp?"})
    assert response.status_code == 200
    assert "Accessibility Protocol" in response.json()["answer"]

    # 4. Transit query
    response = client.post("/api/copilot", json={"prompt": "Is public transit coordinated?"})
    assert response.status_code == 200
    assert "Transit Coordination" in response.json()["answer"]

def test_api_veto_or_approve_inactive(client):
    """Verifies that attempting to veto or approve an inactive zone raises OperatorActionError mapped to HTTP 400."""
    response = client.post("/api/veto", json={"zone_id": "Gate_A"})
    assert response.status_code == 400
    assert "No active proposed safety script found to veto" in response.json()["detail"]

    response = client.post("/api/approve", json={"zone_id": "Gate_A"})
    assert response.status_code == 400
    assert "No active countdown timer found to approve" in response.json()["detail"]

@pytest.mark.anyio
async def test_process_telemetry_invalid_json(orchestrator):
    """Verifies that calling process_telemetry with invalid JSON is handled by TelemetryValidationError and doesn't crash."""
    await orchestrator.process_telemetry("invalid json content")

@pytest.mark.anyio
async def test_process_telemetry_invalid_zone(orchestrator):
    """Verifies that calling process_telemetry with an invalid zone ID is caught, logged, and audited without crashing."""
    import json
    payload = {
        "zone_id": "Non_Existent_Zone",
        "crowd_density": 1.2,
        "flow_rate_in": 10.0,
        "flow_rate_out": 8.0,
        "timestamp": 1234567.0
    }
    await orchestrator.process_telemetry(json.dumps(payload))
    assert "Non_Existent_Zone" not in orchestrator.graph.nodes

def test_api_verify_audit_logs(client, tmp_path):
    """Verifies the cryptographic integrity endpoint /api/audit-logs/verify."""
    from unittest.mock import patch
    temp_log = tmp_path / "temp_audit.jsonl"
    with patch("src.audit.AUDIT_LOG_FILE", str(temp_log)):
        with patch("src.config.AUDIT_LOG_FILE", str(temp_log)):
            # 1. Verification of non-existent/empty log
            response = client.get("/api/audit-logs/verify")
            assert response.status_code == 200
            assert response.json()["verified"] is True
            
            # 2. Write one valid audit log entry
            from src.audit import write_audit_log
            write_audit_log("test_event", {"zone_id": "Gate_A", "detail": "Init test"})
            
            response = client.get("/api/audit-logs/verify")
            assert response.status_code == 200
            assert response.json()["verified"] is True
            
            # 3. Tamper with the log file
            with open(temp_log, "r") as f:
                content = f.read()
            # Tamper by changing a character in the json
            tampered_content = content.replace("test_event", "tampered_event")
            with open(temp_log, "w") as f:
                f.write(tampered_content)
                
            # Verification should now fail
            response = client.get("/api/audit-logs/verify")
            assert response.status_code == 200
            assert response.json()["verified"] is False

