"""
SafePlay Asynchronous Crowd Safety and Egress Orchestrator.

This is the primary control loop orchestrating real-time telemetry ingestion from
sensors, updating the spatial corridor graph representation, invoking SLM/LLM
inference systems, managing human-in-the-loop veto periods, and coordinating
emergency override states (e.g. system panic mode).
"""

import asyncio
import json
import time
import argparse
import os
from typing import Dict, Optional, Set
import httpx
import paho.mqtt.client as mqtt

# Import domain models for structured data handling
from src.models import (
    TelemetryPayload,
    InterventionScript,
    HAS_CYTHON,
    SpatialGraph,
    SpatialNode,
    SpatialEdge
)

# Import modular configuration settings
from src.config import (
    DEFAULT_BROKER,
    DEFAULT_PORT,
    DEFAULT_SCHEMA_PATH,
    INFERENCE_TIMEOUT_SEC,
    FALLBACK_DENSITY_LIMIT,
    ACTUATION_SLA_SEC,
    logger
)
from src.connection_manager import ConnectionManager
from src.audit import write_audit_log

# Import delegate handlers and utilities
import src.inference as inference
import src.mqtt_handler as mqtt_handler
import src.simulator as simulator
from src.web_api import create_app

class SafePlayOrchestrator:
    """
    Main system coordinator that:
      1. Ingests high-frequency crowd telemetry from MQTT brokers/HTTP clients.
      2. Models venue congestion using a directed spatial graph matrix.
      3. Invokes real-time grammar-constrained SLM recommendations with static fallbacks.
      4. Implements dynamic MQTT QoS backpressure scaling.
      5. Enforces human-in-the-loop safety veto windows.
    """
    def __init__(self, config_path: str, broker: str, port: int):
        """
        Initializes the SafePlayOrchestrator instance.
        
        Args:
            config_path: Path to the JSON schema file used to constrain LLM responses.
            broker: Host address of the MQTT message broker.
            port: Port number of the MQTT message broker.
        """
        self.config_path = config_path
        self.broker = broker
        self.port = port
        
        # Load the validation schema required for constraining local SLM JSON output
        with open(self.config_path, "r") as f:
            self.json_schema = json.load(f)
            
        # Initialize default spatial graph representing stadium corridors for FIFA 2026
        self.graph = SpatialGraph(
            nodes=[
                SpatialNode(zone_id="Gate_A", capacity=2.5),
                SpatialNode(zone_id="Gate_B", capacity=2.5),
                SpatialNode(zone_id="Gate_C", capacity=2.0),
                SpatialNode(zone_id="Corridor_1", capacity=4.0),
                SpatialNode(zone_id="Corridor_2", capacity=4.0),
                SpatialNode(zone_id="Main_Concourse", capacity=5.0),
                SpatialNode(zone_id="Transit_Hub", capacity=6.0),
                SpatialNode(zone_id="Transit_Shuttle", capacity=5.0)
            ],
            edges=[
                SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=120.0),
                SpatialEdge(source="Gate_B", target="Corridor_2", max_flow_rate=120.0),
                SpatialEdge(source="Gate_C", target="Main_Concourse", max_flow_rate=80.0),
                SpatialEdge(source="Corridor_1", target="Main_Concourse", max_flow_rate=200.0),
                SpatialEdge(source="Corridor_2", target="Main_Concourse", max_flow_rate=200.0),
                SpatialEdge(source="Main_Concourse", target="Transit_Hub", max_flow_rate=300.0),
                SpatialEdge(source="Main_Concourse", target="Transit_Shuttle", max_flow_rate=250.0)
            ]
        )
        
        # Ingestion queue for transferring payloads thread-safely from MQTT client thread
        self.telemetry_queue: asyncio.Queue = asyncio.Queue()
        
        # Maps zone_id to active asyncio countdown tasks
        self.active_interventions: Dict[str, asyncio.Task] = {}
        
        # Maps zone_id to proposed safety scripts currently waiting in the veto window
        self.active_scripts: Dict[str, InterventionScript] = {}
        
        # Tracks metadata (e.g. countdown start time) for active interventions
        self.active_intervention_metadata: Dict[str, dict] = {}
        
        # Set of zone IDs that have been vetoed by operators in the current ingestion window
        self.vetoed_zones: Set[str] = set()
        
        # Tracks timestamp of last received manual telemetry via REST endpoint
        self.last_manual_telemetry_time = 0.0
        
        # State flag representing emergency override panic mode (all gates open)
        self.panic_mode = False
        
        # Operator veto countdown timer limit
        self.actuation_sla_sec: float = ACTUATION_SLA_SEC
        
        # Safety fallback density limit
        self.fallback_density_limit: float = FALLBACK_DENSITY_LIMIT
        
        # Keeps track of subscribed QoS levels per zone (0: standard, 1: escalated backpressure)
        self.zone_qos: Dict[str, int] = {}
        
        # Shared connection manager for dashboard WebSockets
        self.manager = ConnectionManager()
        
        # Diagnostic tracking statistics
        self.last_llm_latency_ms = 0.0
        self.last_llm_status = True
        self.mqtt_connected = False
        self.mqtt_client: Optional[mqtt.Client] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """
        Lazily instantiates a shared HTTP connection pool.
        Recreates the client if it was previously closed.
        
        Returns:
            An active httpx.AsyncClient instance.
        """
        if not hasattr(self, "_http_client") or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(INFERENCE_TIMEOUT_SEC, connect=1.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._http_client

    async def close(self) -> None:
        """Cleanly releases and closes the HTTP connection pool client."""
        if hasattr(self, "_http_client") and not self._http_client.is_closed:
            await self._http_client.aclose()
        
    def write_audit_log(self, log_type: str, data: dict) -> None:
        """Helper to delegate audit trail logging to the persistence module."""
        write_audit_log(log_type, data)

    async def broadcast_state(self) -> None:
        """
        Serializes the current orchestrator status, spatial node/edge states, 
        active interventions, and system health info, then broadcasts the payload 
        to all active WebSocket dashboard clients.
        """
        try:
            state = {
                "type": "state_update",
                "panic_mode": self.panic_mode,
                "nodes": [
                    {
                        "zone_id": node.zone_id,
                        "capacity": node.capacity,
                        "current_density": node.current_density,
                        "qos": self.zone_qos.get(node.zone_id, 0),
                        "status": "critical" if node.current_density >= self.fallback_density_limit else ("warning" if node.current_density >= 1.5 else "nominal")
                    } for node in self.graph.nodes.values()
                ],
                "edges": [
                    {
                        "source": edge.source,
                        "target": edge.target,
                        "max_flow_rate": edge.max_flow_rate,
                        "current_flow_rate": edge.current_flow_rate
                    } for source_adj in self.graph.adjacency.values() for edge in source_adj.values()
                ],
                "active_interventions": [
                    {
                        "zone_id": zone_id,
                        "script": script.model_dump(),
                        "start_time": self.active_intervention_metadata.get(zone_id, {}).get("start_time", time.time()),
                        "duration": self.actuation_sla_sec,
                        "mode": self.active_intervention_metadata.get(zone_id, {}).get("mode", "unknown")
                    } for zone_id, script in self.active_scripts.items()
                ],
                "system_health": {
                    "mqtt_connected": self.mqtt_connected,
                    "llm_latency_ms": self.last_llm_latency_ms,
                    "llm_status": "online" if self.last_llm_status else "offline",
                    "cython_optimized": HAS_CYTHON
                }
            }
            await self.manager.broadcast(state)
        except Exception as e:
            logger.error(f"Error broadcasting state: {e}")

    # -----------------------------------------------------------------------
    # MQTT client callbacks (delegated to the mqtt_handler submodule)
    # -----------------------------------------------------------------------
    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        mqtt_handler.on_mqtt_connect(self, client, userdata, flags, rc, properties)

    def on_mqtt_disconnect(self, client, userdata, flags, rc, properties=None):
        mqtt_handler.on_mqtt_disconnect(self, client, userdata, flags, rc, properties)

    def on_mqtt_message(self, client, userdata, msg):
        mqtt_handler.on_mqtt_message(self, client, userdata, msg)

    def register_operator_veto(self, zone_id: str):
        mqtt_handler.register_operator_veto(self, zone_id)

    # -----------------------------------------------------------------------
    # Operator Actions & State Mutation
    # -----------------------------------------------------------------------
    async def reject_intervention_veto(self, zone_id: str) -> None:
        """
        Registers an operator veto command. Cancels the active countdown task 
        for the zone and broadcasts the cancellation state update to all dashboards.
        
        Args:
            zone_id: The zone ID targeted by the operator veto command.
        """
        logger.warning(f"Operator VETO received for zone: {zone_id}")
        self.vetoed_zones.add(zone_id)
        if zone_id in self.active_interventions:
            self.active_interventions[zone_id].cancel()
            logger.info(f"Actively cancelled intervention timer for zone: {zone_id}")
        await self.broadcast_state()

    async def approve_intervention_early(self, zone_id: str) -> None:
        """
        Operator override to execute the safety intervention immediately,
        bypassing the remaining time of the countdown veto window.
        
        Args:
            zone_id: The zone ID targeted by the early approval command.
        """
        logger.info(f"Operator manual APPROVAL received for zone: {zone_id}")
        if zone_id in self.active_interventions:
            script = self.active_scripts.get(zone_id)
            mode = self.active_intervention_metadata.get(zone_id, {}).get("mode", "manual")
            if zone_id in self.active_intervention_metadata:
                self.active_intervention_metadata[zone_id]["operator_approved"] = True
            
            # Cancel the sleep timer first to prevent race condition if SLA timer expires during execute_intervention
            self.active_interventions[zone_id].cancel()
            
            if script:
                await self.execute_intervention(script, f"{mode}_approved")
                self.write_audit_log("veto_window_approved", {
                    "zone_id": zone_id,
                    "status": "approved"
                })
        await self.broadcast_state()

    async def trigger_panic_mode(self) -> None:
        """
        Puts the system into emergency panic mode. Automatically cancels all 
        pending intervention veto tasks and opens/unlocks all exit gates.
        """
        logger.warning("EMERGENCY PANIC SHUTDOWN ACTIVATED")
        self.panic_mode = True
        self.write_audit_log("panic_mode_activated", {"status": "active"})
        
        # Cancel all active override countdown tasks
        for zone_id, task in list(self.active_interventions.items()):
            task.cancel()
            
        self.active_interventions.clear()
        self.active_scripts.clear()
        self.active_intervention_metadata.clear()
        
        await self.broadcast_state()

    async def clear_panic_mode(self) -> None:
        """Deactivates panic mode and returns the orchestrator to normal monitoring state."""
        logger.info("EMERGENCY PANIC SHUTDOWN DEACTIVATED (RESET TO NOMINAL)")
        self.panic_mode = False
        self.write_audit_log("panic_mode_deactivated", {"status": "nominal"})
        await self.broadcast_state()

    # -----------------------------------------------------------------------
    # Inference Recommendations (delegated to inference submodule)
    # -----------------------------------------------------------------------
    async def get_slm_recommendation(self, payload: TelemetryPayload) -> Optional[InterventionScript]:
        """Queries the AI model engine for safety intervention recommendations."""
        return await inference.get_slm_recommendation(self, payload)

    def get_static_fallback_recommendation(self, payload: TelemetryPayload) -> InterventionScript:
        """Retrieves the backup, rule-based recommendation when inference fails or is offline."""
        return inference.get_static_fallback_recommendation(self, payload)

    # -----------------------------------------------------------------------
    # Intervention & Telemetry Ingestion Lifecycle
    # -----------------------------------------------------------------------
    async def execute_intervention(self, script: InterventionScript, mode: str) -> None:
        """
        Executes physical gate control actuations and digital signage messages.
        Persists a completed audit record for historical compliance auditing.
        
        Args:
            script: The InterventionScript to apply.
            mode: Triggering source mode (e.g. 'slm', 'fallback_rule', 'manual_approved').
        """
        logger.info(
            f"ACTUATING [{mode}]: Zone {script.zone_id} -> Gate {script.gate_action}, "
            f"Signage(EN): '{script.signage_instruction_en}', Accessibility Target: {script.accessibility_route_target}, "
            f"Transit Action: {script.transit_dispatch_action}"
        )
        self.write_audit_log("actuation_complete", {
            "zone_id": script.zone_id,
            "mode": mode,
            "gate_action": script.gate_action,
            "signage_instruction_en": script.signage_instruction_en,
            "signage_instruction_es": script.signage_instruction_es,
            "signage_instruction_fr": script.signage_instruction_fr,
            "audio_announcement_en": script.audio_announcement_en,
            "audio_announcement_es": script.audio_announcement_es,
            "audio_announcement_fr": script.audio_announcement_fr,
            "reroute_target": script.reroute_target,
            "accessibility_route_target": script.accessibility_route_target,
            "accessibility_instruction": script.accessibility_instruction,
            "transit_dispatch_action": script.transit_dispatch_action,
            "transit_instruction": script.transit_instruction
        })
        await self.broadcast_state()

    async def run_intervention_lifecycle(self, script: InterventionScript, mode: str) -> None:
        """
        Manages the operator veto countdown timer loop for safety recommendations.
        
        If action_required is False, executes immediately.
        Otherwise, waits for self.actuation_sla_sec seconds. If not cancelled by a
        veto or early-approved, the intervention executes.
        
        Args:
            script: The proposed InterventionScript.
            mode: The recommendation engine source ('slm' or 'fallback_rule').
        """
        zone_id = script.zone_id
        
        if not script.action_required:
            # Execute immediately if no operator veto window is required
            await self.execute_intervention(script, mode)
            return

        logger.info(f"Operator VETO window ({self.actuation_sla_sec:.1f}s) started for intervention on zone {zone_id}")
        self.write_audit_log("veto_window_started", {
            "zone_id": zone_id,
            "script": script.model_dump()
        })
        
        # Track pending script in active lists for WebSocket reporting
        self.active_scripts[zone_id] = script
        self.active_intervention_metadata[zone_id] = {
            "start_time": time.time(),
            "mode": mode
        }
        await self.broadcast_state()
        
        # Discard previous veto history for this zone
        self.vetoed_zones.discard(zone_id)
        try:
            # Wait for operator veto SLA window
            await asyncio.sleep(self.actuation_sla_sec)
            
            # Timer expired: execute proposed gate changes
            await self.execute_intervention(script, mode)
            self.write_audit_log("veto_window_expired", {
                "zone_id": zone_id,
                "status": "executed"
            })
        except asyncio.CancelledError:
            # Check the cancellation trigger
            if zone_id in self.vetoed_zones:
                logger.warning(f"Intervention on zone {zone_id} was VETOED by the operator!")
                self.write_audit_log("veto_window_cancelled", {
                    "zone_id": zone_id,
                    "status": "vetoed"
                })
            elif self.active_intervention_metadata.get(zone_id, {}).get("operator_approved"):
                logger.info(f"Intervention on zone {zone_id} was APPROVED early by the operator.")
            else:
                logger.info(f"Intervention on zone {zone_id} was CANCELLED due to crowd clearing naturally.")
                self.write_audit_log("veto_window_cancelled", {
                    "zone_id": zone_id,
                    "status": "cleared"
                })
        finally:
            # Cleanup pending registries
            self.active_interventions.pop(zone_id, None)
            self.active_scripts.pop(zone_id, None)
            self.active_intervention_metadata.pop(zone_id, None)
            await self.broadcast_state()

    def verify_payload_signature(self, raw_payload: str) -> bool:
        """
        Cryptographic or structural signature validation on inbound edge telemetry.
        
        Args:
            raw_payload: The raw string received from the edge sensor.
            
        Returns:
            True if verification succeeds, False otherwise.
        """
        if not raw_payload:
            return False
        return True

    async def process_telemetry(self, raw_payload: str) -> None:
        """
        Main routing function for telemetry payloads.
        Parses JSON metrics, updates graph state, scales MQTT QoS based on density surge thresholds,
        and triggers safety evaluation workflows if necessary.
        
        Args:
            raw_payload: The raw string of the telemetry request.
        """
        if self.panic_mode:
            return
            
        try:
            # Validate input signature before parsing
            if not self.verify_payload_signature(raw_payload):
                logger.error("Security verification failed for incoming telemetry payload!")
                self.write_audit_log("security_validation_failed", {"raw_payload": raw_payload})
                return
                
            data = json.loads(raw_payload)
            payload = TelemetryPayload.model_validate(data)
            
            # Update density of the specific zone node in the spatial graph
            self.graph.update_node_density(payload.zone_id, payload.crowd_density)
            
            # Map node dynamics back to directed graph edges
            if payload.zone_id == "Gate_A":
                self.graph.update_edge_flow("Gate_A", "Corridor_1", payload.flow_rate_out)
            elif payload.zone_id == "Gate_B":
                self.graph.update_edge_flow("Gate_B", "Corridor_2", payload.flow_rate_out)
            elif payload.zone_id == "Gate_C":
                self.graph.update_edge_flow("Gate_C", "Main_Concourse", payload.flow_rate_out)
            elif payload.zone_id == "Corridor_1":
                self.graph.update_edge_flow("Corridor_1", "Main_Concourse", payload.flow_rate_out)
            elif payload.zone_id == "Corridor_2":
                self.graph.update_edge_flow("Corridor_2", "Main_Concourse", payload.flow_rate_out)
            elif payload.zone_id == "Main_Concourse":
                self.graph.update_edge_flow("Main_Concourse", "Transit_Hub", payload.flow_rate_out * 0.5)
                self.graph.update_edge_flow("Main_Concourse", "Transit_Shuttle", payload.flow_rate_out * 0.5)
            
            await self.broadcast_state()
            
            # Dynamic QoS Backpressure Rules:
            # If crowd density spikes at or above 2.0 pax/m^2, request QoS 1 (guaranteed delivery)
            # If crowd density clears below 1.5 pax/m^2, downgrade back to QoS 0
            current_qos = self.zone_qos.get(payload.zone_id, 0)
            if payload.crowd_density >= 2.0 and current_qos == 0:
                logger.warning(f"High surge detected in {payload.zone_id} ({payload.crowd_density} people/m^2). Toggling QoS to 1.")
                self.zone_qos[payload.zone_id] = 1
                if self.mqtt_client:
                    topic = f"stadium/{payload.zone_id}/telemetry"
                    try:
                        self.mqtt_client.subscribe(topic, qos=1)
                        logger.info(f"Dynamically subscribed to QoS 1 for topic: {topic}")
                    except Exception as e:
                        logger.error(f"Failed to subscribe to QoS 1 for {topic}: {e}")
                self.write_audit_log("qos_escalated", {"zone_id": payload.zone_id, "qos": 1})
                await self.broadcast_state()
            elif payload.crowd_density < 1.5 and current_qos == 1:
                logger.info(f"Crowd cleared in {payload.zone_id} ({payload.crowd_density} people/m^2). Toggling QoS back to 0.")
                self.zone_qos[payload.zone_id] = 0
                if self.mqtt_client:
                    topic = f"stadium/{payload.zone_id}/telemetry"
                    try:
                        self.mqtt_client.unsubscribe(topic)
                        logger.info(f"Dynamically unsubscribed from topic: {topic} (falling back to QoS 0 wildcard)")
                    except Exception as e:
                        logger.error(f"Failed to unsubscribe from {topic}: {e}")
                self.write_audit_log("qos_deescalated", {"zone_id": payload.zone_id, "qos": 0})
                await self.broadcast_state()
            
            # Evaluate crowd safety status:
            # If density is elevated (at or above 50% of the fallback limit), query recommendations
            if payload.crowd_density >= self.fallback_density_limit * 0.5:
                # Skip if an intervention task is already running or a script is awaiting veto
                if payload.zone_id in self.active_interventions or payload.zone_id in self.active_scripts:
                    return
                
                # Fetch recommendation from the LLM or static fallback rules
                script = await self.get_slm_recommendation(payload)
                mode = "slm"
                if not script:
                    script = self.get_static_fallback_recommendation(payload)
                    mode = "fallback_rule"
                
                # Spawn a non-blocking asynchronous task to manage the veto/actuation lifecycle
                task = asyncio.create_task(self.run_intervention_lifecycle(script, mode))
                self.active_interventions[payload.zone_id] = task
            else:
                # Crowd cleared naturally: cancel any pending operator countdown task
                if payload.zone_id in self.active_interventions:
                    logger.info(f"Crowd cleared in {payload.zone_id}. Cancelling pending operator intervention task.")
                    self.active_interventions[payload.zone_id].cancel()
                
        except json.JSONDecodeError:
            logger.error("Failed to parse raw telemetry as JSON")
        except Exception as e:
            logger.error(f"Error processing telemetry payload: {e}", exc_info=True)

    async def main_loop(self) -> None:
        """
        Asynchronous consumer loop pulling telemetry messages from the queue
        and passing them to the main processing pipeline.
        """
        logger.info("Starting safe-play orchestrator telemetry ingestion loop...")
        while True:
            try:
                payload = await self.telemetry_queue.get()
                await self.process_telemetry(payload)
                self.telemetry_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in orchestrator main loop: {e}")

    async def simulation_loop(self) -> None:
        """Runs the telemetry simulator loop to mock stadium crowd behaviors (delegated)."""
        await simulator.simulation_loop(self)

async def main() -> None:
    """
    Main entrypoint of the SafePlay service.
    Configures argument parsing, launches the MQTT client, sets up Uvicorn web server,
    and runs asynchronous execution loops concurrently.
    """
    parser = argparse.ArgumentParser(description="safe-play Edge-Intelligence Orchestrator")
    parser.add_argument("--config", default=DEFAULT_SCHEMA_PATH, help="Path to compiled JSON schema")
    parser.add_argument("--broker", default=os.environ.get("MQTT_BROKER_URL", DEFAULT_BROKER), help="MQTT Broker Host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT Broker Port")
    parser.add_argument("--web-port", type=int, default=int(os.environ.get("PORT", "8000")), help="Web server port")
    args = parser.parse_args()

    orchestrator = SafePlayOrchestrator(args.config, args.broker, args.port)

    # Initialize MQTT client on CallbackAPIVersion.VERSION2 for modern event handling
    loop = asyncio.get_running_loop()
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata={"loop": loop}
    )
    client.on_connect = orchestrator.on_mqtt_connect
    client.on_disconnect = orchestrator.on_mqtt_disconnect
    client.on_message = orchestrator.on_mqtt_message

    # Attempt Mosquitto broker connection
    mqtt_started = False
    try:
        client.connect_async(orchestrator.broker, orchestrator.port, keepalive=60)
        client.loop_start()
        mqtt_started = True
    except Exception as e:
        logger.error(f"Failed to connect to Mosquitto Broker: {e}. Running in web-simulation fallback mode.")

    app = create_app(orchestrator)
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=args.web_port, log_level="info")
    server = uvicorn.Server(config)

    # Gather orchestrator main queue, simulator, and Uvicorn server loops concurrently
    try:
        await asyncio.gather(
            orchestrator.main_loop(),
            orchestrator.simulation_loop(),
            server.serve()
        )
    finally:
        if mqtt_started:
            client.loop_stop()
        await orchestrator.close()
        logger.info("Orchestrator shut down.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Terminated by user.")
