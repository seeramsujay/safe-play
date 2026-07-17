import pytest
import json
import asyncio
from unittest.mock import MagicMock
from src.orchestrator import SafePlayOrchestrator

class MockMQTTMessage:
    def __init__(self, topic, payload):
        self.topic = topic
        self.payload = payload

@pytest.mark.anyio
async def test_mqtt_connect_success():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    mock_client = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = False
    
    orchestrator.on_mqtt_connect(
        client=mock_client,
        userdata={"loop": mock_loop},
        flags={},
        rc=0
    )
    
    assert orchestrator.mqtt_connected is True
    assert orchestrator.mqtt_client == mock_client
    # Should subscribe to stadium/+/telemetry and stadium/operator/veto
    assert mock_client.subscribe.call_count == 2
    mock_client.subscribe.assert_any_call("stadium/+/telemetry", qos=0)
    mock_client.subscribe.assert_any_call("stadium/operator/veto", qos=1)

@pytest.mark.anyio
async def test_mqtt_connect_failure():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    mock_client = MagicMock()
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = False
    
    orchestrator.on_mqtt_connect(
        client=mock_client,
        userdata={"loop": mock_loop},
        flags={},
        rc=5 # Connection refused
    )
    
    assert orchestrator.mqtt_connected is False
    assert orchestrator.mqtt_client is None
    mock_client.subscribe.assert_not_called()

@pytest.mark.anyio
async def test_mqtt_disconnect_callback():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    orchestrator.mqtt_connected = True
    mock_client = MagicMock()
    orchestrator.mqtt_client = mock_client
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = False
    
    orchestrator.on_mqtt_disconnect(
        client=mock_client,
        userdata={"loop": mock_loop},
        flags={},
        rc=1
    )

    
    assert orchestrator.mqtt_connected is False
    assert orchestrator.mqtt_client is None

@pytest.mark.anyio
async def test_mqtt_message_telemetry_queuing():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    payload = {
        "zone_id": "Gate_A",
        "crowd_density": 1.2,
        "flow_rate_in": 20.0,
        "flow_rate_out": 15.0,
        "timestamp": 1720875600.0
    }
    raw_payload = json.dumps(payload).encode("utf-8")
    msg = MockMQTTMessage("stadium/Gate_A/telemetry", raw_payload)
    
    # We pass the running loop in userdata
    loop = asyncio.get_running_loop()
    orchestrator.on_mqtt_message(None, {"loop": loop}, msg)
    
    # Allow small tick for call_soon_threadsafe to run
    await asyncio.sleep(0.01)
    
    queued = orchestrator.telemetry_queue.get_nowait()
    assert json.loads(queued)["zone_id"] == "Gate_A"

@pytest.mark.anyio
async def test_mqtt_message_veto_handling():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    payload = {"zone_id": "Gate_A"}
    raw_payload = json.dumps(payload).encode("utf-8")
    msg = MockMQTTMessage("stadium/operator/veto", raw_payload)
    
    mock_loop = MagicMock()
    
    orchestrator.on_mqtt_message(None, {"loop": mock_loop}, msg)
    
    # Verify that the register_operator_veto callback is queued to loop
    mock_loop.call_soon_threadsafe.assert_called_once_with(
        orchestrator.register_operator_veto, "Gate_A"
    )

@pytest.mark.anyio
async def test_mqtt_message_unsupported_topic():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    msg = MockMQTTMessage("stadium/invalid/topic", b"some_payload")
    
    mock_loop = MagicMock()
    orchestrator.on_mqtt_message(None, {"loop": mock_loop}, msg)
    
    mock_loop.call_soon_threadsafe.assert_not_called()
    assert orchestrator.telemetry_queue.empty()

@pytest.mark.anyio
async def test_mqtt_message_malformed_veto():
    orchestrator = SafePlayOrchestrator("config/schema.json", "127.0.0.1", 1883)
    # Sending invalid JSON to veto topic
    msg = MockMQTTMessage("stadium/operator/veto", b"invalid-json")
    
    mock_loop = MagicMock()
    # This should log error but not raise any exception
    orchestrator.on_mqtt_message(None, {"loop": mock_loop}, msg)
    
    mock_loop.call_soon_threadsafe.assert_not_called()
