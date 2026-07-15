import asyncio
import json
import logging
import time
import argparse
import sys
import random
import os
from typing import Dict, Optional, Set, List
from pydantic import BaseModel, Field
import httpx
import paho.mqtt.client as mqtt

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

from src.models import TelemetryPayload, InterventionScript, HAS_CYTHON, SpatialGraph, SpatialNode, SpatialEdge

# Setup structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Orchestrator")

# Constants
DEFAULT_BROKER = "127.0.0.1"
DEFAULT_PORT = 1883
DEFAULT_SCHEMA_PATH = "config/schema.json"
INFERENCE_TIMEOUT_SEC = 0.1  # 100ms timeout
FALLBACK_DENSITY_LIMIT = 3.0  # people/m^2
ACTUATION_SLA_SEC = 15.0  # 15 seconds
AUDIT_LOG_FILE = "logs/audit_trail.jsonl"

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        async def send(conn: WebSocket):
            try:
                await conn.send_json(message)
            except Exception:
                pass
        
        # Copy the list to prevent modification during iteration
        connections = list(self.active_connections)
        if connections:
            await asyncio.gather(*(send(c) for c in connections))

class SafePlayOrchestrator:
    def __init__(self, config_path: str, broker: str, port: int):
        self.config_path = config_path
        self.broker = broker
        self.port = port
        
        # Load schema
        with open(self.config_path, "r") as f:
            self.json_schema = json.load(f)
            
        # Initialize default spatial graph
        self.graph = SpatialGraph(
            nodes=[
                SpatialNode(zone_id="Gate_A", capacity=2.5),
                SpatialNode(zone_id="Gate_B", capacity=2.5),
                SpatialNode(zone_id="Corridor_1", capacity=4.0),
                SpatialNode(zone_id="Corridor_2", capacity=4.0),
                SpatialNode(zone_id="Main_Concourse", capacity=5.0)
            ],
            edges=[
                SpatialEdge(source="Gate_A", target="Corridor_1", max_flow_rate=120.0),
                SpatialEdge(source="Gate_B", target="Corridor_2", max_flow_rate=120.0),
                SpatialEdge(source="Corridor_1", target="Main_Concourse", max_flow_rate=200.0),
                SpatialEdge(source="Corridor_2", target="Main_Concourse", max_flow_rate=200.0)
            ]
        )
        
        # Ingestion queue for thread-safe transfer from MQTT callback
        self.telemetry_queue: asyncio.Queue = asyncio.Queue()
        
        # Active veto flags/timers
        self.active_interventions: Dict[str, asyncio.Task] = {}
        self.active_scripts: Dict[str, InterventionScript] = {}
        self.active_intervention_metadata: Dict[str, dict] = {}
        self.vetoed_zones: Set[str] = set()
        self.last_manual_telemetry_time = 0.0
        self.panic_mode = False
        self.actuation_sla_sec: float = ACTUATION_SLA_SEC
        self.fallback_density_limit: float = FALLBACK_DENSITY_LIMIT
        
        # Ensure audit log directory exists
        log_dir = os.path.dirname(AUDIT_LOG_FILE) or "."
        os.makedirs(log_dir, exist_ok=True)
        
        # QoS level tracker per zone (default is QoS 0)
        self.zone_qos: Dict[str, int] = {}
        
        # Web server state tracking
        self.manager = ConnectionManager()
        self.last_llm_latency_ms = 0.0
        self.last_llm_status = True
        self.mqtt_connected = False
        self.mqtt_client: Optional[mqtt.Client] = None

    @property
    def http_client(self) -> httpx.AsyncClient:
        """Lazily initialise a shared async HTTP client; recreate if closed."""
        if not hasattr(self, "_http_client") or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(INFERENCE_TIMEOUT_SEC, connect=1.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._http_client

    async def close(self):
        if hasattr(self, "_http_client") and not self._http_client.is_closed:
            await self._http_client.aclose()
        
    def write_audit_log(self, log_type: str, data: dict):
        """Append-only audit trail logging"""
        log_entry = {
            "timestamp": time.time(),
            "event_type": log_type,
            **data
        }
        with open(AUDIT_LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry) + "\n")
        logger.info(f"Audit Trail Written [{log_type}]: {data.get('zone_id', 'global')}")

    async def broadcast_state(self):
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
                        "status": "critical" if node.current_density >= FALLBACK_DENSITY_LIMIT else ("warning" if node.current_density >= 1.5 else "nominal")
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
                        "duration": ACTUATION_SLA_SEC,
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

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        loop = userdata.get("loop")
        if rc == 0:
            logger.info("Connected to MQTT Broker successfully")
            self.mqtt_connected = True
            self.mqtt_client = client
            client.subscribe("stadium/+/telemetry", qos=0)
            client.subscribe("stadium/operator/veto", qos=1)
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.mqtt_connected = False
            self.mqtt_client = None
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_state(), loop)

    def on_mqtt_disconnect(self, client, userdata, flags, rc, properties=None):
        logger.warning(f"Disconnected from MQTT Broker: rc={rc}")
        self.mqtt_connected = False
        self.mqtt_client = None
        loop = userdata.get("loop")
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast_state(), loop)

    def on_mqtt_message(self, client, userdata, msg):
        loop = userdata.get("loop")
        if not loop:
            return
            
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8")
        
        if topic.startswith("stadium/") and topic.endswith("/telemetry"):
            # Put incoming telemetry on queue for main loop processing
            loop.call_soon_threadsafe(self.telemetry_queue.put_nowait, payload_str)
        elif topic == "stadium/operator/veto":
            try:
                data = json.loads(payload_str)
                zone_id = data.get("zone_id")
                if zone_id:
                    loop.call_soon_threadsafe(self.register_operator_veto, zone_id)
            except Exception as e:
                logger.error(f"Failed to parse veto payload: {e}")

    def register_operator_veto(self, zone_id: str):
        """Thread-safe veto registration from MQTT callback thread."""
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(self.reject_intervention_veto(zone_id), loop)
        except RuntimeError:
            # No running loop — mark veto directly (edge case: called before loop starts)
            self.vetoed_zones.add(zone_id)
            task = self.active_interventions.get(zone_id)
            if task and not task.done():
                task.cancel()

    async def reject_intervention_veto(self, zone_id: str):
        logger.warning(f"Operator VETO received for zone: {zone_id}")
        self.vetoed_zones.add(zone_id)
        if zone_id in self.active_interventions:
            self.active_interventions[zone_id].cancel()
            logger.info(f"Actively cancelled intervention timer for zone: {zone_id}")
        await self.broadcast_state()

    async def approve_intervention_early(self, zone_id: str):
        logger.info(f"Operator manual APPROVAL received for zone: {zone_id}")
        if zone_id in self.active_interventions:
            script = self.active_scripts.get(zone_id)
            mode = self.active_intervention_metadata.get(zone_id, {}).get("mode", "manual")
            if script:
                if zone_id in self.active_intervention_metadata:
                    self.active_intervention_metadata[zone_id]["operator_approved"] = True
                await self.execute_intervention(script, f"{mode}_approved")
                self.write_audit_log("veto_window_approved", {
                    "zone_id": zone_id,
                    "status": "approved"
                })
            # Cancel the sleep timer, which will trigger cleanup in finally block
            self.active_interventions[zone_id].cancel()
        await self.broadcast_state()

    async def trigger_panic_mode(self):
        logger.warning("EMERGENCY PANIC SHUTDOWN ACTIVATED")
        self.panic_mode = True
        self.write_audit_log("panic_mode_activated", {"status": "active"})
        
        # Cancel all active override tasks
        for zone_id, task in list(self.active_interventions.items()):
            task.cancel()
        self.active_interventions.clear()
        self.active_scripts.clear()
        self.active_intervention_metadata.clear()
        
        await self.broadcast_state()

    async def clear_panic_mode(self):
        logger.info("EMERGENCY PANIC SHUTDOWN DEACTIVATED (RESET TO NOMINAL)")
        self.panic_mode = False
        self.write_audit_log("panic_mode_deactivated", {"status": "nominal"})
        await self.broadcast_state()

    async def get_slm_recommendation(self, payload: TelemetryPayload) -> Optional[InterventionScript]:
        """
        Queries local llama-server under schema constraints. 
        Times out in 100ms to maintain sub-second prefill target.
        """
        alt_route = self.graph.get_alternative_route(payload.zone_id)
        
        prompt = (
            f"STAD_ZONE: {payload.zone_id}\n"
            f"DENSITY: {payload.crowd_density:.2f}\n"
            f"FLOW_IN: {payload.flow_rate_in:.2f}\n"
            f"FLOW_OUT: {payload.flow_rate_out:.2f}\n"
            f"ALT_ROUTE: {alt_route or 'NONE'}\n"
            f"Assess crowd hazard and recommend signage/gate intervention."
        )
        
        # Call llama-server via completions endpoint
        url = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8080/completion")
        req_payload = {
            "prompt": prompt,
            "temperature": 0.0,
            "stream": False,
            "n_predict": 128,
            "json_schema": self.json_schema,
            "stop": ["\n\n"],
        }
        
        start_time = time.time()
        try:
            response = await self.http_client.post(url, json=req_payload)
                
            latency_ms = (time.time() - start_time) * 1000.0
            
            if response.status_code == 200:
                resp_json = response.json()
                content = resp_json.get("content", "").strip()
                parsed_content = json.loads(content)
                script = InterventionScript.model_validate(parsed_content)
                
                self.last_llm_latency_ms = latency_ms
                self.last_llm_status = True
                self.write_audit_log("inference_success", {
                    "zone_id": payload.zone_id,
                    "latency_ms": latency_ms,
                    "response": parsed_content
                })
                return script
            else:
                logger.error(f"llama-server error: {response.status_code} {response.text}")
                self.last_llm_latency_ms = latency_ms
                self.last_llm_status = False
                
        except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError, Exception) as e:
            latency_ms = (time.time() - start_time) * 1000.0
            logger.warning(f"Inference engine unavailable or timed out ({latency_ms:.1f}ms). Reason: {type(e).__name__}")
            self.last_llm_latency_ms = latency_ms
            self.last_llm_status = False
            self.write_audit_log("inference_fallback", {
                "zone_id": payload.zone_id,
                "latency_ms": latency_ms,
                "error": str(e)
            })
            
        return None

    def get_static_fallback_recommendation(self, payload: TelemetryPayload) -> InterventionScript:
        """
        Rule-based backup that executes immediately when inference engine is offline or times out.
        """
        alt_route = self.graph.get_alternative_route(payload.zone_id)
        
        if payload.crowd_density >= FALLBACK_DENSITY_LIMIT:
            return InterventionScript(
                zone_id=payload.zone_id,
                hazard_level="critical",
                action_required=True,
                reroute_target=alt_route,
                signage_instruction=f"CRITICAL OVERLOAD. USE ROUTE {alt_route or 'NEAREST EXIT'}",
                gate_action="CLOSE_IMMEDIATELY",
                rationale="Fallback: density limit exceeded"
            )
        else:
            return InterventionScript(
                zone_id=payload.zone_id,
                hazard_level="medium",
                action_required=False,
                reroute_target=None,
                signage_instruction="PLEASE KEEP MOVING",
                gate_action="SLOW_ENTRY",
                rationale="Fallback: density elevated"
            )

    async def execute_intervention(self, script: InterventionScript, mode: str):
        """Actuate gates and digital signs"""
        logger.info(f"ACTUATING [{mode}]: Zone {script.zone_id} -> Gate {script.gate_action}, Signage: '{script.signage_instruction}'")
        self.write_audit_log("actuation_complete", {
            "zone_id": script.zone_id,
            "mode": mode,
            "gate_action": script.gate_action,
            "signage_instruction": script.signage_instruction,
            "reroute_target": script.reroute_target
        })
        await self.broadcast_state()

    async def run_intervention_lifecycle(self, script: InterventionScript, mode: str):
        """
        Manages the lifecycle of an intervention recommendation.
        If an action is required, it initiates a human-in-the-loop countdown window (SLA timeout).
        If the countdown expires without operator veto, it proceeds to execute the intervention.
        If the operator vetoes or approves early, the task handles the CancelledError and adjusts state.
        """
        zone_id = script.zone_id
        
        if not script.action_required:
            # Execute immediately if no action/veto window is required by schema
            await self.execute_intervention(script, mode)
            return

        # Explicit Human-In-The-Loop 2-second SLA timer window
        logger.info(f"Operator VETO window (2.0s) started for intervention on zone {zone_id}")
        self.write_audit_log("veto_window_started", {
            "zone_id": zone_id,
            "script": script.model_dump()
        })
        
        self.active_scripts[zone_id] = script
        self.active_intervention_metadata[zone_id] = {
            "start_time": time.time(),
            "mode": mode
        }
        await self.broadcast_state()
        
        self.vetoed_zones.discard(zone_id)
        try:
            await asyncio.sleep(ACTUATION_SLA_SEC)
            # SLA timer expired without Veto
            await self.execute_intervention(script, mode)
            self.write_audit_log("veto_window_expired", {
                "zone_id": zone_id,
                "status": "executed"
            })
        except asyncio.CancelledError:
            # Check if this was a veto or early approval or natural clearing
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
            self.active_interventions.pop(zone_id, None)
            self.active_scripts.pop(zone_id, None)
            self.active_intervention_metadata.pop(zone_id, None)
            await self.broadcast_state()

    def verify_payload_signature(self, raw_payload: str) -> bool:
        """
        Stub for cryptographic signature validation on incoming edge telemetry.
        In production, this validates HMAC-SHA256 signatures or client certificate verification.
        """
        if not raw_payload:
            return False
        # Placeholder verification: check if payload has essential structure
        return True

    async def process_telemetry(self, raw_payload: str):
        if self.panic_mode:
            return
        try:
            # 1. Basic verification/decryption stub (mTLS handles channel)
            if not self.verify_payload_signature(raw_payload):
                logger.error("Security verification failed for incoming telemetry payload!")
                self.write_audit_log("security_validation_failed", {"raw_payload": raw_payload})
                return
                
            data = json.loads(raw_payload)
            payload = TelemetryPayload.model_validate(data)
            
            # 2. Update local spatial graph node
            self.graph.update_node_density(payload.zone_id, payload.crowd_density)
            # Simple mapping to edges
            if payload.zone_id == "Gate_A":
                self.graph.update_edge_flow("Gate_A", "Corridor_1", payload.flow_rate_out)
            elif payload.zone_id == "Gate_B":
                self.graph.update_edge_flow("Gate_B", "Corridor_2", payload.flow_rate_out)
            elif payload.zone_id == "Corridor_1":
                self.graph.update_edge_flow("Corridor_1", "Main_Concourse", payload.flow_rate_out)
            elif payload.zone_id == "Corridor_2":
                self.graph.update_edge_flow("Corridor_2", "Main_Concourse", payload.flow_rate_out)
            
            await self.broadcast_state()
            
            # 3. Dynamic Backpressure rules:
            # If crowd density is high, we signal backpressure to MQTT broker
            # (Toggle zone client QoS from 0 up to QoS 1 to guarantee delivery)
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
            
            # 4. Trigger triage evaluations if density is elevated
            if payload.crowd_density >= self.fallback_density_limit * 0.5:
                # If there is already an active intervention script in the operator veto window, let it run
                # If there is already an active/pending intervention task or script, let it run
                if payload.zone_id in self.active_interventions or payload.zone_id in self.active_scripts:
                    return
                
                # Fetch recommendation (SLM or fallback)
                script = await self.get_slm_recommendation(payload)
                mode = "slm"
                if not script:
                    script = self.get_static_fallback_recommendation(payload)
                    mode = "fallback_rule"
                
                # Run lifecycle task with 2-second operator override window
                task = asyncio.create_task(self.run_intervention_lifecycle(script, mode))
                self.active_interventions[payload.zone_id] = task
            else:
                # Crowd has cleared naturally below warning threshold (1.5)
                # Cancel the pending operator veto window if it exists
                if payload.zone_id in self.active_interventions:
                    logger.info(f"Crowd cleared in {payload.zone_id}. Cancelling pending operator intervention task.")
                    self.active_interventions[payload.zone_id].cancel()
                
        except json.JSONDecodeError:
            logger.error("Failed to parse raw telemetry as JSON")
        except Exception as e:
            logger.error(f"Error processing telemetry payload: {e}", exc_info=True)

    async def main_loop(self):
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

    async def simulation_loop(self):
        """
        Periodically injects fluctuating mock telemetry to show the dashboard alive.
        Every 30 seconds, it triggers a crowd surge at Gate_A or Gate_B.
        """
        logger.info("Starting live telemetry simulation task...")
        zones = ["Gate_A", "Gate_B", "Corridor_1", "Corridor_2", "Main_Concourse"]
        tick = 0
        while True:
            try:
                await asyncio.sleep(2.0)
                if time.time() - self.last_manual_telemetry_time < 15.0:
                    continue
                tick += 1
                
                # Alternate surges between Gate_A and Gate_B
                is_gate_a_surge = (tick % 15 == 0)
                is_gate_b_surge = (tick % 15 == 7)
                
                for zone in zones:
                    # Respect vetoes/approvals
                    if zone in self.vetoed_zones:
                        # Vetoed: simulate cleared crowd
                        density = 0.7 + random.uniform(-0.1, 0.1)
                        flow_in = 12.0 + random.uniform(-2, 2)
                        flow_out = 14.0 + random.uniform(-2, 2)
                    elif zone in self.active_scripts:
                        # Surge is active and pending operator action: sustain elevated values
                        if zone == "Gate_A":
                            density = 3.5 + random.uniform(-0.2, 0.2)
                            flow_in = 92.0 + random.uniform(-5, 5)
                            flow_out = 18.0 + random.uniform(-2, 2)
                        elif zone == "Gate_B":
                            density = 2.3 + random.uniform(-0.1, 0.1)
                            flow_in = 48.0 + random.uniform(-4, 4)
                            flow_out = 32.0 + random.uniform(-3, 3)
                        else:
                            density = 2.5 + random.uniform(-0.2, 0.2)
                            flow_in = 60.0 + random.uniform(-5, 5)
                            flow_out = 40.0 + random.uniform(-4, 4)
                    elif zone == "Gate_A" and is_gate_a_surge:
                        density = 3.5 + random.uniform(-0.2, 0.2)
                        flow_in = 92.0 + random.uniform(-5, 5)
                        flow_out = 18.0 + random.uniform(-2, 2)
                        logger.warning("Simulation: Triggering crowd surge at Gate_A!")
                    elif zone == "Gate_B" and is_gate_b_surge:
                        density = 2.3 + random.uniform(-0.1, 0.1)
                        flow_in = 48.0 + random.uniform(-4, 4)
                        flow_out = 32.0 + random.uniform(-3, 3)
                        logger.warning("Simulation: Triggering elevated congestion at Gate_B!")
                    else:
                        # Nominal stadium fluctuations
                        if zone.startswith("Gate"):
                            density = 1.0 + random.uniform(-0.2, 0.2)
                            flow_in = 20.0 + random.uniform(-3, 3)
                            flow_out = 18.0 + random.uniform(-3, 3)
                        elif zone.startswith("Corridor"):
                            density = 0.8 + random.uniform(-0.15, 0.15)
                            flow_in = 18.0 + random.uniform(-3, 3)
                            flow_out = 16.0 + random.uniform(-3, 3)
                        else:
                            density = 1.2 + random.uniform(-0.2, 0.2)
                            flow_in = 36.0 + random.uniform(-5, 5)
                            flow_out = 34.0 + random.uniform(-5, 5)
                    
                    density = max(0.1, round(density, 2))
                    flow_in = max(0.0, round(flow_in, 1))
                    flow_out = max(0.0, round(flow_out, 1))
                    
                    payload = {
                        "zone_id": zone,
                        "crowd_density": density,
                        "flow_rate_in": flow_in,
                        "flow_rate_out": flow_out,
                        "timestamp": time.time()
                    }
                    
                    # Queue the mock telemetry so it flows through full processing pipeline
                    self.telemetry_queue.put_nowait(json.dumps(payload))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in simulation loop: {e}")

# ---------------------------------------------------------------------------
# Pydantic request models — validate API inputs instead of accepting raw dict
# ---------------------------------------------------------------------------
class ZoneActionRequest(BaseModel):
    zone_id: str = Field(..., min_length=1, max_length=64)

class TelemetryRequest(BaseModel):
    zone_id: str = Field(..., min_length=1, max_length=64)
    crowd_density: float = Field(..., ge=0.0, le=20.0)
    flow_rate_in: float = Field(..., ge=0.0)
    flow_rate_out: float = Field(..., ge=0.0)
    timestamp: float = Field(..., gt=0.0)

class ConfigUpdateRequest(BaseModel):
    actuation_sla_sec: Optional[float] = Field(None, ge=2.0, le=300.0)
    fallback_density_limit: Optional[float] = Field(None, ge=0.5, le=10.0)

def create_app(orchestrator: SafePlayOrchestrator) -> FastAPI:
    app = FastAPI(
        title="EdgePulse 2026 Stadium Intelligence API",
        description="Real-time crowd safety orchestration for FIFA World Cup 2026 venues.",
        version="0.1.0",
    )

    # Serve static files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(current_dir, "static")

    @app.get("/")
    async def get_index():
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                return HTMLResponse(content=f.read(), status_code=200)
        return HTMLResponse(content="<h1>static/index.html not found!</h1>", status_code=404)

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await orchestrator.manager.connect(websocket)
        try:
            # Send initial state update immediately
            await orchestrator.broadcast_state()
            while True:
                # Keep connection alive
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            orchestrator.manager.disconnect(websocket)

    @app.post("/api/veto")
    async def post_veto(payload: ZoneActionRequest):
        await orchestrator.reject_intervention_veto(payload.zone_id)
        return {"status": "success", "zone_id": payload.zone_id}

    @app.post("/api/approve")
    async def post_approve(payload: ZoneActionRequest):
        await orchestrator.approve_intervention_early(payload.zone_id)
        return {"status": "success", "zone_id": payload.zone_id}

    @app.post("/api/panic")
    async def post_panic():
        await orchestrator.trigger_panic_mode()
        return {"status": "success", "panic_mode": True}

    @app.post("/api/panic/clear")
    async def post_panic_clear():
        await orchestrator.clear_panic_mode()
        return {"status": "success", "panic_mode": False}

    @app.post("/api/telemetry")
    async def post_telemetry(payload: TelemetryRequest):
        orchestrator.last_manual_telemetry_time = time.time()
        orchestrator.telemetry_queue.put_nowait(payload.model_dump_json())
        return {"status": "success", "message": "Telemetry queued"}

    @app.get("/api/audit-logs")
    async def get_audit_logs(limit: int = 100):
        """Return the last `limit` audit log entries (max 500)."""
        limit = min(max(limit, 1), 500)
        logs: list[dict] = []
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r") as f:
                for line in f:
                    stripped = line.strip()
                    if stripped:
                        try:
                            logs.append(json.loads(stripped))
                        except json.JSONDecodeError:
                            pass  # Skip malformed lines silently
                        if len(logs) > 500:
                            # Trim early to cap memory: keep a rolling window
                            logs = logs[-500:]
        return logs[-limit:]

    @app.get("/api/config")
    async def get_config():
        return {
            "actuation_sla_sec": orchestrator.actuation_sla_sec,
            "fallback_density_limit": orchestrator.fallback_density_limit,
            "broker": orchestrator.broker,
            "port": orchestrator.port,
        }

    @app.post("/api/config")
    async def post_config(payload: ConfigUpdateRequest):
        """Update runtime config on the orchestrator instance (no global mutation)."""
        if payload.actuation_sla_sec is not None:
            orchestrator.actuation_sla_sec = payload.actuation_sla_sec
        if payload.fallback_density_limit is not None:
            orchestrator.fallback_density_limit = payload.fallback_density_limit
        await orchestrator.broadcast_state()
        return {
            "status": "success",
            "actuation_sla_sec": orchestrator.actuation_sla_sec,
            "fallback_density_limit": orchestrator.fallback_density_limit,
        }

    return app

async def main():
    parser = argparse.ArgumentParser(description="safe-play Edge-Intelligence Orchestrator")
    parser.add_argument("--config", default=DEFAULT_SCHEMA_PATH, help="Path to compiled JSON schema")
    parser.add_argument("--broker", default=os.environ.get("MQTT_BROKER_URL", DEFAULT_BROKER), help="MQTT Broker Host")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="MQTT Broker Port")
    parser.add_argument("--web-port", type=int, default=int(os.environ.get("PORT", "8000")), help="Web server port")
    args = parser.parse_args()

    orchestrator = SafePlayOrchestrator(args.config, args.broker, args.port)

    # Initialize MQTT client using CallbackAPIVersion.VERSION2
    loop = asyncio.get_running_loop()
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        userdata={"loop": loop}
    )
    client.on_connect = orchestrator.on_mqtt_connect
    client.on_disconnect = orchestrator.on_mqtt_disconnect
    client.on_message = orchestrator.on_mqtt_message

    # Connect to local broker (optional on boot, to permit cloud running)
    mqtt_started = False
    try:
        client.connect(orchestrator.broker, orchestrator.port, keepalive=60)
        client.loop_start()
        mqtt_started = True
    except Exception as e:
        logger.error(f"Failed to connect to Mosquitto Broker: {e}. Running in web-simulation fallback mode.")

    app = create_app(orchestrator)
    config = uvicorn.Config(app, host="0.0.0.0", port=args.web_port, log_level="info")
    server = uvicorn.Server(config)

    # Run the ingestion orchestrator loop, simulation loop, and web server concurrently
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
