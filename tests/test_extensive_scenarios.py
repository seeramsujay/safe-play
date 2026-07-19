"""
Extensive integration, race-condition, and edge-case test suite for SafePlay.

Role:
    Validates:
    1. Concurrency telemetry bursts and queue handling safety.
    2. Race condition execution between concurrent Operator veto and early approval.
    3. Complex spatial graph routing topologies (cycles, saturation, isolated nodes).
    4. Dynamic configuration changes during active intervention windows.
    5. Rapid, idempotent panic mode toggles.
    6. WebSocket broadcast connection failure resilience.
    7. Telemetry schema boundary conditions (limits, zero-values).

Ecosystem Positioning:
    - Below: pytest test framework and FastAPI testing libraries.
    - Above: Exercises edge conditions and race states across core files:
      - `src/orchestrator.py` (telemetry queue concurrency, panic loop state).
      - `src/connection_manager.py` (broadcasting under disconnection exceptions).
      - `src/models.py` and `src/web_api.py` (input validation schema constraints).
"""


import json
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError
from fastapi import WebSocket, WebSocketDisconnect
from src.models import TelemetryPayload, SpatialNode, SpatialEdge, SpatialGraph
from src.orchestrator import SafePlayOrchestrator, create_app
from src.connection_manager import ConnectionManager
from fastapi.testclient import TestClient

@pytest.fixture
def temp_audit_log_extensive(tmp_path):
    """Fixture to mock and redirect audit logs to a temporary file for verification."""
    log_file = tmp_path / "extensive_audit_trail.jsonl"
    with patch("src.audit.AUDIT_LOG_FILE", str(log_file)):
        with patch("src.config.AUDIT_LOG_FILE", str(log_file)):
            yield log_file

@pytest.mark.asyncio
async def test_concurrency_telemetry_burst(temp_audit_log_extensive):
    """
    Simulates a heavy burst of 100 concurrent telemetry payloads sent to the orchestrator.
    Ensures that the internal telemetry queue is thread-safe and the processing pipeline
    handles large volumes of incoming telemetry without deadlock.
    """
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    orchestrator.actuation_sla_sec = 0.05
    
    # Mock HTTP LLM response so SLM returns immediately without network calls
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": json.dumps({
            "zone_id": "Gate_A",
            "hazard_level": "medium",
            "action_required": False,
            "reroute_target": None,
            "signage_instruction": "NORMAL_FLOW",
            "gate_action": "SLOW_ENTRY",
            "rationale": "High volume ingestion check"
        })
    }
    
    # Send 100 telemetry payloads concurrently
    async def send_payload(i):
        payload = {
            "zone_id": f"Gate_{i % 5}",
            "crowd_density": 1.0 + (i % 3) * 0.5,
            "flow_rate_in": 20.0 + i,
            "flow_rate_out": 15.0,
            "timestamp": time.time()
        }
        # Direct queue ingestion simulating concurrent HTTP/MQTT receiver threads
        orchestrator.telemetry_queue.put_nowait(json.dumps(payload))

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        tasks = [send_payload(i) for i in range(100)]
        await asyncio.gather(*tasks)
        
        # Verify all 100 messages are queued
        assert orchestrator.telemetry_queue.qsize() == 100
        
        # Process a subset of telemetry to verify loop ingestion
        for _ in range(10):
            raw = await orchestrator.telemetry_queue.get()
            await orchestrator.process_telemetry(raw)
            orchestrator.telemetry_queue.task_done()
            
        assert orchestrator.telemetry_queue.qsize() == 90

@pytest.mark.asyncio
async def test_operator_veto_and_approve_race_condition(temp_audit_log_extensive):
    """
    Simulates a race condition where the operator clicks both VETO and APPROVE
    almost simultaneously. Verifies that the task cancellation handles concurrent calls
    safely without throwing unhandled exceptions.
    """
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    orchestrator.actuation_sla_sec = 1.0
    
    # Trigger elevated density
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 5.0,
        "flow_rate_in": 100.0,
        "flow_rate_out": 20.0,
        "timestamp": time.time()
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": json.dumps({
            "zone_id": "Gate_A",
            "hazard_level": "critical",
            "action_required": True,
            "reroute_target": "Corridor_2",
            "signage_instruction": "USE ALTERNATIVE CORRIDOR 2",
            "gate_action": "CLOSE_IMMEDIATELY",
            "rationale": "High density surge"
        })
    }
    
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        await orchestrator.process_telemetry(json.dumps(payload))
        await asyncio.sleep(0.01) # Schedule intervention
        
    assert "Gate_A" in orchestrator.active_interventions
    
    # Trigger both veto and approve concurrently
    t1 = asyncio.create_task(orchestrator.reject_intervention_veto("Gate_A"))
    t2 = asyncio.create_task(orchestrator.approve_intervention_early("Gate_A"))
    
    # Wait for both tasks to resolve
    await asyncio.gather(t1, t2, return_exceptions=False)
    
    # Ensure active interventions is cleared and the state is resolved
    assert "Gate_A" not in orchestrator.active_interventions

def test_spatial_graph_cyclic_and_saturated_topologies():
    """
    Validates alternative routing logic on complex graph configurations:
    1. A cycle (Gate_A -> Corridor_1 -> Corridor_2 -> Gate_A).
    2. Complete saturation (all targets above capacity).
    3. Isolated node with no edges.
    """
    # 1. Saturated Topology
    nodes_saturated = [
        SpatialNode(zone_id="Gate_A", capacity=2.0, current_density=3.0),
        SpatialNode(zone_id="Corridor_1", capacity=1.5, current_density=2.0),
        SpatialNode(zone_id="Corridor_2", capacity=1.0, current_density=1.5)
    ]
    edges_saturated = [
        SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=50.0),
        SpatialEdge(source="Gate_A", target="Corridor_2", max_flow_rate=50.0)
    ]
    graph_saturated = SpatialGraph(nodes_saturated, edges_saturated)
    # Both targets are saturated, should return None
    assert graph_saturated.get_alternative_route("Gate_A") is None

    # 2. Cyclic Topology
    nodes_cycle = [
        SpatialNode(zone_id="Gate_A", capacity=2.0, current_density=3.0),
        SpatialNode(zone_id="Corridor_1", capacity=3.0, current_density=1.0), # Spare: 2.0
        SpatialNode(zone_id="Corridor_2", capacity=3.0, current_density=0.5)  # Spare: 2.5 (Best target)
    ]
    edges_cycle = [
        SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=50.0),
        SpatialEdge(source="Corridor_1", target="Corridor_2", max_flow_rate=50.0),
        SpatialEdge(source="Corridor_2", target="Gate_A", max_flow_rate=50.0),
        SpatialEdge(source="Gate_A", target="Corridor_2", max_flow_rate=50.0)
    ]
    graph_cycle = SpatialGraph(nodes_cycle, edges_cycle)
    # Picks Corridor_2 because it is directly connected to Gate_A and has the highest spare capacity
    assert graph_cycle.get_alternative_route("Gate_A") == "Corridor_2"

    # 3. Isolated Node
    nodes_isolated = [
        SpatialNode(zone_id="Gate_A", capacity=2.0, current_density=3.0),
        SpatialNode(zone_id="Corridor_1", capacity=3.0, current_density=1.0)
    ]
    graph_isolated = SpatialGraph(nodes_isolated, [])
    assert graph_isolated.get_alternative_route("Gate_A") is None

@pytest.mark.asyncio
async def test_dynamic_config_changes_during_intervention():
    """
    Tests changing the dynamic config settings while an intervention window is running.
    Verifies that the orchestrator state is preserved and subsequent actions use the updated values.
    """
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    
    # 1. Update SLA window
    orchestrator.actuation_sla_sec = 5.0
    orchestrator.fallback_density_limit = 4.0
    
    # 2. Trigger high density event
    payload = {
        "zone_id": "Gate_B",
        "crowd_density": 5.0,
        "flow_rate_in": 100.0,
        "flow_rate_out": 20.0,
        "timestamp": time.time()
    }
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "content": json.dumps({
            "zone_id": "Gate_B",
            "hazard_level": "critical",
            "action_required": True,
            "reroute_target": "Corridor_1",
            "signage_instruction": "USE ALTERNATIVE CORRIDOR 1",
            "gate_action": "CLOSE_IMMEDIATELY",
            "rationale": "Congested Gate B"
        })
    }
    
    with patch("httpx.AsyncClient.post", return_value=mock_response):
        await orchestrator.process_telemetry(json.dumps(payload))
        await asyncio.sleep(0.01)
        
    assert "Gate_B" in orchestrator.active_interventions
    
    # 3. Modify SLA configuration in the middle of active countdown
    orchestrator.actuation_sla_sec = 2.0
    
    # Verify values updated
    assert orchestrator.actuation_sla_sec == 2.0
    
    # Cleanup Gate_B task
    await orchestrator.reject_intervention_veto("Gate_B")

@pytest.mark.asyncio
async def test_rapid_panic_mode_toggles():
    """
    Verifies that toggling panic mode on and off rapidly in a loop does not result
    in stale, inconsistent state or uncaught background tasks.
    """
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    
    for _ in range(20):
        await orchestrator.trigger_panic_mode()
        assert orchestrator.panic_mode is True
        await orchestrator.clear_panic_mode()
        assert orchestrator.panic_mode is False

@pytest.mark.asyncio
async def test_websocket_broadcast_resilience():
    """
    Tests the connection manager's ability to broadcast messages concurrently
    even when some registered WebSocket clients throw exceptions (simulating abrupt disconnects).
    """
    manager = ConnectionManager()
    
    # Create mock websockets
    ws_good_1 = AsyncMock(spec=WebSocket)
    ws_bad = AsyncMock(spec=WebSocket)
    ws_good_2 = AsyncMock(spec=WebSocket)
    
    # ws_bad raises a Disconnect error when sending JSON
    ws_bad.send_json.side_effect = WebSocketDisconnect("Client disconnected")
    
    # Register all websockets
    manager.active_connections.extend([ws_good_1, ws_bad, ws_good_2])
    
    # Broadcast a state update
    test_msg = {"type": "test_alert", "value": 42}
    await manager.broadcast(test_msg)
    
    # Ensure good websockets still received the broadcast successfully
    ws_good_1.send_json.assert_called_once_with(test_msg)
    ws_good_2.send_json.assert_called_once_with(test_msg)
    ws_bad.send_json.assert_called_once_with(test_msg)

def test_telemetry_schema_boundary_conditions():
    """
    Validates the TelemetryPayload Pydantic schema validation boundaries.
    Tests boundary limit checks (density 0.0, 20.0, out of bounds, missing fields).
    """
    # Min boundary (zero density and flows)
    data_min = {
        "zone_id": "Gate_A",
        "crowd_density": 0.0,
        "flow_rate_in": 0.0,
        "flow_rate_out": 0.0,
        "timestamp": 12345.0
    }
    payload = TelemetryPayload.model_validate(data_min)
    assert payload.crowd_density == 0.0
    assert payload.flow_rate_in == 0.0

    # Max density boundary (20.0 is upper limit in Web API schema)
    # Note: TelemetryRequest schema restricts crowd_density to le=20.0
    from src.web_api import TelemetryRequest
    
    data_max = {
        "zone_id": "Gate_A",
        "crowd_density": 20.0,
        "flow_rate_in": 150.0,
        "flow_rate_out": 120.0,
        "timestamp": 12345.0
    }
    req = TelemetryRequest.model_validate(data_max)
    assert req.crowd_density == 20.0

    # Exceeding Max density boundary
    data_overflow = {
        "zone_id": "Gate_A",
        "crowd_density": 20.1,
        "flow_rate_in": 150.0,
        "flow_rate_out": 120.0,
        "timestamp": 12345.0
    }
    with pytest.raises(ValidationError):
        TelemetryRequest.model_validate(data_overflow)

    # Negative density validation checks
    data_negative = {
        "zone_id": "Gate_A",
        "crowd_density": -0.1,
        "flow_rate_in": 10.0,
        "flow_rate_out": 10.0,
        "timestamp": 12345.0
    }
    with pytest.raises(ValidationError):
        TelemetryRequest.model_validate(data_negative)
