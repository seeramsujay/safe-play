"""
Unit tests for SafePlay schemas, spatial nodes/edges, and audit trail verification.

Role:
    Validates Pydantic schema validation boundaries for incoming telemetry and generated safety scripts,
    ensures structural JSON-schema integrity, checks graph pathfinding constraints under overload,
    and tests cryptographic ledger tampering detection.

Ecosystem Positioning:
    - Below: pytest test runner.
    - Above: Validates schema classes and validation logic defined in `src/models.py`
      and ledger integrity verification in `src/audit.py`.
"""

import json
import pytest
from pydantic import ValidationError
from src.models import TelemetryPayload, InterventionScript, SpatialNode, SpatialEdge

def test_telemetry_payload_valid():
    # A valid payload
    payload_data = {
        "zone_id": "Gate_A",
        "crowd_density": 1.8,
        "flow_rate_in": 45.0,
        "flow_rate_out": 30.0,
        "timestamp": 1720875600.0
    }
    payload = TelemetryPayload.model_validate(payload_data)
    assert payload.zone_id == "Gate_A"
    assert payload.crowd_density == 1.8

def test_telemetry_payload_extra_fields():
    # Extra fields should raise validation error due to extra="forbid"
    payload_data = {
        "zone_id": "Gate_A",
        "crowd_density": 1.8,
        "flow_rate_in": 45.0,
        "flow_rate_out": 30.0,
        "timestamp": 1720875600.0,
        "unsupported_field": "some_value"
    }
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(payload_data)

def test_telemetry_payload_missing_fields():
    # Missing fields should raise validation error
    payload_data = {
        "zone_id": "Gate_A",
        "crowd_density": 1.8
    }
    with pytest.raises(ValidationError):
        TelemetryPayload.model_validate(payload_data)

def test_intervention_script_valid():
    # A valid script
    script_data = {
        "zone_id": "Gate_A",
        "hazard_level": "medium",
        "action_required": True,
        "reroute_target": "Corridor_2",
        "signage_instruction_en": "USE ALTERNATIVE GATE B",
        "signage_instruction_es": "USE PUERTA B ALTERNATIVA",
        "signage_instruction_fr": "UTILISER LA PORTE B ALTERNATIVE",
        "audio_announcement_en": "Please use alternative gate B",
        "audio_announcement_es": "Por favor use la puerta alternativa B",
        "audio_announcement_fr": "S'il vous plaît utiliser la porte alternative B",
        "gate_action": "SLOW_ENTRY",
        "accessibility_route_target": "Gate_B_ADA",
        "accessibility_instruction": "ADA ramp available at Gate B",
        "transit_dispatch_action": "INCREASE_SHUTTLE_FREQUENCY",
        "transit_instruction": "Deploy additional shuttles",
        "rationale": "High density detected"
    }
    script = InterventionScript.model_validate(script_data)
    assert script.zone_id == "Gate_A"
    assert script.action_required is True
    assert script.reroute_target == "Corridor_2"
    assert script.signage_instruction_en == "USE ALTERNATIVE GATE B"

def test_intervention_script_extra_fields():
    # Extra fields should raise validation error due to extra="forbid"
    script_data = {
        "zone_id": "Gate_A",
        "hazard_level": "medium",
        "action_required": True,
        "reroute_target": "Corridor_2",
        "signage_instruction_en": "USE ALTERNATIVE GATE B",
        "signage_instruction_es": "USE PUERTA B ALTERNATIVA",
        "signage_instruction_fr": "UTILISER LA PORTE B ALTERNATIVE",
        "audio_announcement_en": "Please use alternative gate B",
        "audio_announcement_es": "Por favor use la puerta alternativa B",
        "audio_announcement_fr": "S'il vous plaît utiliser la porte alternative B",
        "gate_action": "SLOW_ENTRY",
        "accessibility_route_target": "Gate_B_ADA",
        "accessibility_instruction": "ADA ramp available at Gate B",
        "transit_dispatch_action": "INCREASE_SHUTTLE_FREQUENCY",
        "transit_instruction": "Deploy additional shuttles",
        "rationale": "High density",
        "extra_info": "unauthorized"
    }
    with pytest.raises(ValidationError):
        InterventionScript.model_validate(script_data)

def test_compiled_schema_integrity():
    # Load config/schema.json and verify config properties
    with open("config/schema.json", "r") as f:
        schema = json.load(f)
    assert schema.get("additionalProperties") is False
    assert "zone_id" in schema["properties"]
    assert "hazard_level" in schema["properties"]
    assert "action_required" in schema["properties"]
    assert "signage_instruction_en" in schema["properties"]
    assert "signage_instruction_es" in schema["properties"]
    assert "signage_instruction_fr" in schema["properties"]
    assert "audio_announcement_en" in schema["properties"]
    assert "audio_announcement_es" in schema["properties"]
    assert "audio_announcement_fr" in schema["properties"]
    assert "gate_action" in schema["properties"]
    assert "accessibility_route_target" in schema["properties"]
    assert "accessibility_instruction" in schema["properties"]
    assert "transit_dispatch_action" in schema["properties"]
    assert "transit_instruction" in schema["properties"]
    assert "rationale" in schema["properties"]

def test_spatial_node_validation():
    node = SpatialNode(zone_id="Gate_A", capacity=2.5)
    assert node.zone_id == "Gate_A"
    assert node.capacity == 2.5
    assert node.current_density == 0.0
    
    with pytest.raises(ValidationError):
        SpatialNode(zone_id="Gate_A")

def test_spatial_edge_validation():
    edge = SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=120.0)
    assert edge.source == "Gate_A"
    assert edge.target == "Corridor_1"
    assert edge.max_flow_rate == 120.0
    assert edge.current_flow_rate == 0.0
    
    with pytest.raises(ValidationError):
        SpatialEdge(source="Gate_A", target="Corridor_1")

def test_spatial_graph_pathfinding():
    from src.models import SpatialGraph
    
    nodes = [
        SpatialNode(zone_id="A", capacity=2.0, current_density=0.0),
        SpatialNode(zone_id="B", capacity=2.0, current_density=0.0),
        SpatialNode(zone_id="C", capacity=2.0, current_density=0.0),
        SpatialNode(zone_id="D", capacity=2.0, current_density=0.0)
    ]
    edges = [
        SpatialEdge(source="A", target="B", max_flow_rate=10.0),
        SpatialEdge(source="B", target="C", max_flow_rate=10.0),
        SpatialEdge(source="C", target="D", max_flow_rate=10.0)
    ]
    
    graph = SpatialGraph(nodes, edges)
    
    # 1. Successful path find
    path = graph.find_optimal_egress_path("A", ["D"])
    assert path == ["A", "B", "C", "D"]
    
    # 2. Blocked path due to congestion
    graph.update_node_density("B", 3.0)  # B is now overloaded (density 3.0 > capacity 2.0)
    path = graph.find_optimal_egress_path("A", ["D"])
    assert path is None


def test_cryptographic_audit_log_verification(tmp_path, monkeypatch):
    import os
    from src.audit import write_audit_log, verify_audit_trail
    import src.audit as audit
    
    # Override audit log file to a temp directory path to isolate this test
    temp_log_file = os.path.join(tmp_path, "test_audit_trail.jsonl")
    monkeypatch.setattr(audit, "AUDIT_LOG_FILE", temp_log_file)
    
    # 1. Clear files if any, verify empty file passes
    if os.path.exists(temp_log_file):
        os.remove(temp_log_file)
        
    assert verify_audit_trail() is True
    
    # 2. Write some logs
    write_audit_log("test_event_1", {"zone_id": "Gate_A", "info": "first log"})
    write_audit_log("test_event_2", {"zone_id": "Gate_B", "info": "second log"})
    
    # Verify the chain is valid
    assert verify_audit_trail() is True
    
    # 3. Read the file, alter a line, and verify it detects tampering
    with open(temp_log_file, "r") as f:
        lines = f.readlines()
    
    assert len(lines) == 2
    
    # Let's tamper with the first line's info
    import json
    data = json.loads(lines[0])
    data["info"] = "tampered info"
    lines[0] = json.dumps(data) + "\n"
    
    with open(temp_log_file, "w") as f:
        f.writelines(lines)
        
    # Validation should now fail
    assert verify_audit_trail() is False


