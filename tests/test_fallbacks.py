import pytest
import unittest.mock as mock
import httpx
from src.models import TelemetryPayload, SpatialNode, SpatialEdge, SpatialGraph
from src.orchestrator import SafePlayOrchestrator

def test_spatial_graph_alternative_route():
    # Setup node densities
    nodes = [
        SpatialNode(zone_id="Gate_A", capacity=2.5, current_density=3.2),  # Overloaded
        SpatialNode(zone_id="Corridor_1", capacity=4.0, current_density=1.0), # Good candidate
        SpatialNode(zone_id="Corridor_2", capacity=4.0, current_density=3.8)  # Near capacity
    ]
    edges = [
        SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=100.0),
        SpatialEdge(source="Gate_A", target="Corridor_2", max_flow_rate=100.0)
    ]
    graph = SpatialGraph(nodes, edges)
    
    # Get alternative route from Gate_A
    alt_route = graph.get_alternative_route("Gate_A")
    # Corridor_1 has 3.0 spare capacity (4.0 - 1.0)
    # Corridor_2 has 0.2 spare capacity (4.0 - 3.8)
    # It should pick Corridor_1
    assert alt_route == "Corridor_1"

def test_static_fallback_recommendation():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    
    # Telemetry below threshold
    telemetry_low = TelemetryPayload(
        zone_id="Gate_A",
        crowd_density=1.2,
        flow_rate_in=20.0,
        flow_rate_out=15.0,
        timestamp=1720875600.0
    )
    script_low = orchestrator.get_static_fallback_recommendation(telemetry_low)
    assert script_low.hazard_level == "medium"
    assert script_low.action_required is False
    assert script_low.gate_action == "SLOW_ENTRY"
    
    # Telemetry above threshold (>= 3.0)
    telemetry_high = TelemetryPayload(
        zone_id="Gate_A",
        crowd_density=3.5,
        flow_rate_in=80.0,
        flow_rate_out=20.0,
        timestamp=1720875600.0
    )
    script_high = orchestrator.get_static_fallback_recommendation(telemetry_high)
    assert script_high.hazard_level == "critical"
    assert script_high.action_required is True
    assert script_high.gate_action == "CLOSE_IMMEDIATELY"

@pytest.mark.asyncio
async def test_orchestrator_slm_failure_fallback():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    
    # Telemetry payload that triggers warning/action
    telemetry = TelemetryPayload(
        zone_id="Gate_A",
        crowd_density=3.5,
        flow_rate_in=80.0,
        flow_rate_out=20.0,
        timestamp=1720875600.0
    )
    
    # Mock httpx.AsyncClient.post to raise TimeoutException to simulate offline/slow SLM
    with mock.patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
        script = await orchestrator.get_slm_recommendation(telemetry)
        
        # When SLM fails/times out, get_slm_recommendation returns None
        assert script is None
        
        # Fallback to static rule recommendation should occur in processing loop
        fallback_script = orchestrator.get_static_fallback_recommendation(telemetry)
        assert fallback_script.hazard_level == "critical"
        assert fallback_script.gate_action == "CLOSE_IMMEDIATELY"
