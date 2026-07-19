"""
End-to-End Integration Testing for SafePlay Orchestration and API.

Role:
    Exercises the full system lifecycle including telemetry ingestion, spatial corridor graph
    evaluation, model query mocking, WebSocket client state updates, operator veto/approve
    command API execution, panic mode toggle, and cryptographic audit ledger appending.

Ecosystem Positioning:
    - Below: pytest runner and FastAPI TestClient.
    - Above: Coordinates integration test validation across `src/orchestrator.py`,
      `src/web_api.py`, `src/audit.py`, and `src/models.py`.
"""

import pytest
import json
import asyncio
import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from src.orchestrator import SafePlayOrchestrator, create_app

@pytest.fixture
def temp_audit_log(tmp_path):
    # Patch AUDIT_LOG_FILE to write to a temp file during tests
    log_file = tmp_path / "audit_trail.jsonl"
    with patch("src.audit.AUDIT_LOG_FILE", str(log_file)):
        with patch("src.config.AUDIT_LOG_FILE", str(log_file)):
            yield log_file

@pytest.mark.anyio
async def test_end_to_end_orchestrator_lifecycle(temp_audit_log):
    # Ensure GEMINI_API_KEY is empty so the llama-server path is tested
    with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
        # 1. Initialize Orchestrator with mock broker settings
        orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
        
        # Configure low SLA countdown so tests run fast
        orchestrator.actuation_sla_sec = 0.05
        
        # Set up mock MQTT client to verify subscription actions
        mock_mqtt = MagicMock()
        orchestrator.mqtt_client = mock_mqtt
        orchestrator.mqtt_connected = True
        
        # Create FastAPI app and TestClient
        app = create_app(orchestrator)
        with TestClient(app) as client:
            # Mock successful SLM response
            slm_mock_response = {
                "zone_id": "Gate_A",
                "hazard_level": "critical",
                "action_required": True,
                "reroute_target": "Corridor_2",
                "signage_instruction_en": "USE ALTERNATIVE CORRIDOR 2",
                "signage_instruction_es": "USE CORREDOR ALTERNATIVO 2",
                "signage_instruction_fr": "UTILISER LE COULOIR ALTERNATIF 2",
                "audio_announcement_en": "Please use alternative corridor two",
                "audio_announcement_es": "Por favor use el corredor alternativo dos",
                "audio_announcement_fr": "S'il vous plaît utiliser le couloir alternatif deux",
                "gate_action": "CLOSE_IMMEDIATELY",
                "accessibility_route_target": "Corridor_2_ADA",
                "accessibility_instruction": "Use ADA-compliant ramp next to Corridor 2",
                "transit_dispatch_action": "INCREASE_SHUTTLE_FREQUENCY",
                "transit_instruction": "Dispatch 2 additional shuttles to Gate B",
                "rationale": "High density surge detected in Gate A"
            }
            
            # 2. Establish WebSocket connection to monitor live updates
            with client.websocket_connect("/ws") as websocket:
                # Check initial state update on connection
                initial_msg = websocket.receive_json()
                assert initial_msg["type"] == "state_update"
                assert initial_msg["panic_mode"] is False
                assert len(initial_msg["nodes"]) == 8
                
                # 3. Simulate high density telemetry ingestion (triggers QoS escalation and SLM recommendation)
                telemetry_payload = {
                    "zone_id": "Gate_A",
                    "crowd_density": 5.0,
                    "flow_rate_in": 100.0,
                    "flow_rate_out": 20.0,
                    "timestamp": time.time()
                }
                
                # Mock the HTTP response from the LLM server
                mock_response = MagicMock()
                mock_response.status_code = 200
                # For llama-server, we expect {"content": "<json_string>"}
                mock_response.json.return_value = {
                    "content": json.dumps(slm_mock_response)
                }
                
                with patch("httpx.AsyncClient.post", return_value=mock_response):
                    await orchestrator.process_telemetry(json.dumps(telemetry_payload))
                    await asyncio.sleep(0.01)  # Yield control to allow loop scheduling
                    
                # Verify QoS escalated to 1
                assert orchestrator.zone_qos["Gate_A"] == 1
                mock_mqtt.subscribe.assert_called_with("stadium/Gate_A/telemetry", qos=1)
                
                # Verify active intervention task created
                assert "Gate_A" in orchestrator.active_interventions
                assert "Gate_A" in orchestrator.active_scripts
                assert orchestrator.active_scripts["Gate_A"].gate_action == "CLOSE_IMMEDIATELY"
                
                # Verify WebSocket received state_update containing active intervention
                active_ints = []
                for _ in range(5):
                    try:
                        ws_msg = websocket.receive_json()
                        if ws_msg.get("type") == "state_update":
                            active_ints = ws_msg.get("active_interventions", [])
                            if len(active_ints) > 0:
                                break
                    except Exception:
                        break
                
                assert len(active_ints) == 1
                assert active_ints[0]["zone_id"] == "Gate_A"
                assert active_ints[0]["script"]["gate_action"] == "CLOSE_IMMEDIATELY"
                
                # 4. Wait for SLA window to naturally expire (non-vetoed automatic execution)
                await asyncio.sleep(0.06)
                
                # Verify intervention completed and cleared from active states
                assert "Gate_A" not in orchestrator.active_interventions
                assert "Gate_A" not in orchestrator.active_scripts
                
                # Read audit trail file to verify correct events are appended
                with open(temp_audit_log, "r") as f:
                    logs = [json.loads(line) for line in f]
                    
                event_types = [log["event_type"] for log in logs]
                assert "qos_escalated" in event_types
                assert "veto_window_started" in event_types
                assert "actuation_complete" in event_types
                assert "veto_window_expired" in event_types
                
                # 5. Test Operator VETO lifecycle
                # Trigger elevated density again to schedule a new intervention
                telemetry_payload_veto = {
                    "zone_id": "Gate_B",
                    "crowd_density": 4.0,
                    "flow_rate_in": 90.0,
                    "flow_rate_out": 30.0,
                    "timestamp": time.time()
                }
                
                slm_mock_response_b = slm_mock_response.copy()
                slm_mock_response_b["zone_id"] = "Gate_B"
                mock_response.json.return_value = {
                    "content": json.dumps(slm_mock_response_b)
                }
                
                with patch("httpx.AsyncClient.post", return_value=mock_response):
                    await orchestrator.process_telemetry(json.dumps(telemetry_payload_veto))
                    await asyncio.sleep(0.01)
                    
                assert "Gate_B" in orchestrator.active_interventions
                
                # Trigger operator veto via API
                response = client.post("/api/veto", json={"zone_id": "Gate_B"})
                assert response.status_code == 200
                assert response.json()["status"] == "success"
                
                await asyncio.sleep(0.01)  # Yield to cancel task
                assert "Gate_B" not in orchestrator.active_interventions
                assert "Gate_B" in orchestrator.vetoed_zones
                
                # Verify veto was recorded in audit logs
                with open(temp_audit_log, "r") as f:
                    logs = [json.loads(line) for line in f]
                assert logs[-1]["event_type"] == "veto_window_cancelled"
                assert logs[-1]["status"] == "vetoed"
                
                # 6. Test Operator Early Approval lifecycle
                telemetry_payload_approve = {
                    "zone_id": "Gate_A",
                    "crowd_density": 4.5,
                    "flow_rate_in": 95.0,
                    "flow_rate_out": 25.0,
                    "timestamp": time.time()
                }
                
                mock_response.json.return_value = {
                    "content": json.dumps(slm_mock_response)
                }
                
                with patch("httpx.AsyncClient.post", return_value=mock_response):
                    await orchestrator.process_telemetry(json.dumps(telemetry_payload_approve))
                    await asyncio.sleep(0.01)
                    
                assert "Gate_A" in orchestrator.active_interventions
                
                # Approve the action early
                response = client.post("/api/approve", json={"zone_id": "Gate_A"})
                assert response.status_code == 200
                assert response.json()["status"] == "success"
                
                await asyncio.sleep(0.01)
                assert "Gate_A" not in orchestrator.active_interventions
                
                with open(temp_audit_log, "r") as f:
                    logs = [json.loads(line) for line in f]
                event_types = [log["event_type"] for log in logs]
                assert "veto_window_approved" in event_types
                
                # 7. Test Panic Mode activation & configuration updates
                response = client.post("/api/panic")
                assert response.status_code == 200
                assert response.json()["panic_mode"] is True
                assert orchestrator.panic_mode is True
                
                # Verify new telemetry is ignored during panic mode
                await orchestrator.process_telemetry(json.dumps(telemetry_payload))
                await asyncio.sleep(0.01)
                assert "Gate_A" not in orchestrator.active_interventions
                
                # Clear panic mode
                response = client.post("/api/panic/clear")
                assert response.status_code == 200
                assert response.json()["panic_mode"] is False
                assert orchestrator.panic_mode is False
                
                # 8. Test natural crowd clearing cancelling the veto window
                with patch("httpx.AsyncClient.post", return_value=mock_response):
                    await orchestrator.process_telemetry(json.dumps(telemetry_payload))
                    await asyncio.sleep(0.01)
                assert "Gate_A" in orchestrator.active_interventions
                
                # Send telemetry below warning threshold (1.2) before SLA expires
                cleared_payload = {
                    "zone_id": "Gate_A",
                    "crowd_density": 1.0,
                    "flow_rate_in": 15.0,
                    "flow_rate_out": 10.0,
                    "timestamp": time.time()
                }
                await orchestrator.process_telemetry(json.dumps(cleared_payload))
                await asyncio.sleep(0.01)
                
                # Verify active intervention task was cancelled
                assert "Gate_A" not in orchestrator.active_interventions
                with open(temp_audit_log, "r") as f:
                    logs = [json.loads(line) for line in f]
                assert logs[-1]["event_type"] == "veto_window_cancelled"
                assert logs[-1]["status"] == "cleared"
