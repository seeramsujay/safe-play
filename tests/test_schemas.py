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

