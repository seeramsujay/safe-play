import json
import pytest
from pydantic import ValidationError
from src.models import TelemetryPayload, InterventionScript

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
        "signage_instruction": "USE ALTERNATIVE GATE B",
        "gate_action": "SLOW_ENTRY",
        "rationale": "High density detected"
    }
    script = InterventionScript.model_validate(script_data)
    assert script.zone_id == "Gate_A"
    assert script.action_required is True
    assert script.reroute_target == "Corridor_2"

def test_intervention_script_extra_fields():
    # Extra fields should raise validation error due to extra="forbid"
    script_data = {
        "zone_id": "Gate_A",
        "hazard_level": "medium",
        "action_required": True,
        "reroute_target": "Corridor_2",
        "signage_instruction": "USE ALTERNATIVE GATE B",
        "gate_action": "SLOW_ENTRY",
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
    assert "signage_instruction" in schema["properties"]
    assert "gate_action" in schema["properties"]
    assert "rationale" in schema["properties"]
