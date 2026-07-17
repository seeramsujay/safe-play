"""
MQTT Callback Handlers for SafePlay.

This module processes asynchronous message events from the paho-mqtt network client thread 
and dispatches them thread-safely to the main asyncio event loop executing the 
orchestration logic and FastAPI server.
"""

import asyncio
import json
from src.config import logger

def on_mqtt_connect(orchestrator, client, userdata, flags, rc, properties=None) -> None:
    """
    Callback executed when the MQTT client successfully establishes a connection with the broker.
    
    Subscribes to telemetry topics and operator command channels, and schedules a dashboard broadcast.
    
    Args:
        orchestrator: The main system Orchestrator instance.
        client: The Paho MQTT Client instance.
        userdata: Shared dictionary context, containing the running asyncio loop instance.
        flags: Response flags sent by the broker.
        rc: Connection result code (0 represents successful connection).
        properties: Optional MQTT v5 properties.
    """
    loop = userdata.get("loop")
    if rc == 0:
        logger.info("Connected to MQTT Broker successfully")
        orchestrator.mqtt_connected = True
        orchestrator.mqtt_client = client
        
        # Subscribe to all telemetry feeds with Quality of Service 0 (fire and forget)
        client.subscribe("stadium/+/telemetry", qos=0)
        
        # Subscribe to operator veto commands with Quality of Service 1 (guaranteed delivery)
        client.subscribe("stadium/operator/veto", qos=1)
    else:
        logger.error(f"MQTT connection failed with code {rc}")
        orchestrator.mqtt_connected = False
        orchestrator.mqtt_client = None
        
    if loop and loop.is_running():
        # Dispatch dashboard update state update thread-safely to the main event loop
        asyncio.run_coroutine_threadsafe(orchestrator.broadcast_state(), loop)

def on_mqtt_disconnect(orchestrator, client, userdata, flags, rc, properties=None) -> None:
    """
    Callback executed when the MQTT client disconnects from the message broker.
    
    Args:
        orchestrator: The main system Orchestrator instance.
        client: The Paho MQTT Client instance.
        userdata: Shared dictionary context, containing the running asyncio loop instance.
        flags: Response flags sent by the broker.
        rc: Connection result code.
        properties: Optional MQTT v5 properties.
    """
    logger.warning(f"Disconnected from MQTT Broker: rc={rc}")
    orchestrator.mqtt_connected = False
    orchestrator.mqtt_client = None
    loop = userdata.get("loop")
    if loop and loop.is_running():
        # Update dashboard metrics thread-safely to show the offline status
        asyncio.run_coroutine_threadsafe(orchestrator.broadcast_state(), loop)

def on_mqtt_message(orchestrator, client, userdata, msg) -> None:
    """
    Callback executed when a message is received from a subscribed MQTT topic.
    
    Routes payload messages to appropriate handlers on the main asyncio thread.
    
    Args:
        orchestrator: The main system Orchestrator instance.
        client: The Paho MQTT Client instance.
        userdata: Shared dictionary context, containing the running asyncio loop.
        msg: The MQTT Message instance containing topic and raw payload bytes.
    """
    loop = userdata.get("loop")
    if not loop:
        return
        
    topic = msg.topic
    payload_str = msg.payload.decode("utf-8")
    
    # Check if the message is sensor telemetry data
    if topic.startswith("stadium/") and topic.endswith("/telemetry"):
        # Queue incoming telemetry thread-safely on the main loop queue
        loop.call_soon_threadsafe(orchestrator.telemetry_queue.put_nowait, payload_str)
    # Check if the message is an operator override/veto command
    elif topic == "stadium/operator/veto":
        try:
            data = json.loads(payload_str)
            zone_id = data.get("zone_id")
            if zone_id:
                # Dispatch veto registration thread-safely
                loop.call_soon_threadsafe(orchestrator.register_operator_veto, zone_id)
        except Exception as e:
            logger.error(f"Failed to parse veto payload: {e}")

def register_operator_veto(orchestrator, zone_id: str) -> None:
    """
    Thread-safe veto registration helper called from the MQTT callback thread.
    Queries the main event loop to cancel pending countdown alerts for a specific zone.
    
    Args:
        orchestrator: The active orchestrator instance.
        zone_id: The target quadrant zone identifier to apply the veto override on.
    """
    try:
        loop = asyncio.get_running_loop()
        # Cancel countdown asynchronously on the running event loop
        asyncio.run_coroutine_threadsafe(orchestrator.reject_intervention_veto(zone_id), loop)
    except RuntimeError:
        # Fallback if the event loop is not yet running or accessible:
        # directly mutate state structures and cancel active tasks directly
        orchestrator.vetoed_zones.add(zone_id)
        task = orchestrator.active_interventions.get(zone_id)
        if task and not task.done():
            task.cancel()
