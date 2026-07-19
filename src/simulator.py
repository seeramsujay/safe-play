"""
Mock Ingestion Telemetry Simulator for SafePlay.

Role:
    Runs a background simulation loop that generates realistic crowd telemetry payloads
    (fluctuating densities and flow rates) and simulates periodic surges at gate zones.
    This serves to test the real-time alerting, operator SLA approval workflows, and routing logic
    without requiring physical camera sensors or smart turnstiles to be online.

Ecosystem Positioning:
    - Below: Builtin libraries (`asyncio`, `random`, `json`, `time`, `hmac`, `hashlib`).
    - Above: Instantiated and run within `src/orchestrator.py` during boot time
      if a mock ingestion mode is active. Pushes telemetry to `orchestrator.telemetry_queue`.
"""


import asyncio
import hashlib
import hmac
import json
import os
import random
import time

from src.config import logger

async def simulation_loop(orchestrator) -> None:
    """
    Periodically injects fluctuating mock telemetry to simulate live stadium crowds.
    
    - Runs every 2 seconds.
    - Suspends itself if recent manual telemetry has been received within the last 15 seconds.
    - Triggers alternating crowd surges at Gate_A or Gate_B to test operator intervention alerts.
    
    Args:
        orchestrator: The active orchestrator instance where telemetry data is queued.
    """
    logger.info("Starting live telemetry simulation task...")
    zones = ["Gate_A", "Gate_B", "Gate_C", "Corridor_1", "Corridor_2", "Main_Concourse", "Transit_Hub", "Transit_Shuttle"]
    tick = 0
    
    while True:
        try:
            await asyncio.sleep(2.0)
            
            # Throttle simulator if operator is manually sending telemetry via the HTTP API
            if time.time() - orchestrator.last_manual_telemetry_time < 15.0:
                continue
                
            tick += 1
            
            # Alternate crowd surges between Gate_A (every 30s) and Gate_B (shifted by 14s)
            is_gate_a_surge = (tick % 15 == 0)
            is_gate_b_surge = (tick % 15 == 7)
            
            for zone in zones:
                # 1. Simulating Vetoed State:
                # If operator vetoed an action, show density dropping back to nominal limits
                if zone in orchestrator.vetoed_zones:
                    density = 0.7 + random.uniform(-0.1, 0.1)
                    flow_in = 12.0 + random.uniform(-2, 2)
                    flow_out = 14.0 + random.uniform(-2, 2)
                    
                # 2. Simulating Active SLA Intervention Window State:
                # If there is a pending recommendation script, sustain elevated density values
                elif zone in orchestrator.active_scripts:
                    if zone == "Gate_A":
                        density = 3.5 + random.uniform(-0.2, 0.2)
                        flow_in = 92.0 + random.uniform(-5, 5)
                        flow_out = 18.0 + random.uniform(-2, 2)
                    elif zone == "Gate_B":
                        density = 2.3 + random.uniform(-0.1, 0.1)
                        flow_in = 48.0 + random.uniform(-4, 4)
                        flow_out = 32.0 + random.uniform(-3, 3)
                    elif zone == "Gate_C":
                        density = 2.4 + random.uniform(-0.1, 0.1)
                        flow_in = 40.0 + random.uniform(-3, 3)
                        flow_out = 28.0 + random.uniform(-3, 3)
                    else:
                        density = 2.5 + random.uniform(-0.2, 0.2)
                        flow_in = 60.0 + random.uniform(-5, 5)
                        flow_out = 40.0 + random.uniform(-4, 4)
                        
                # 3. Simulate Surge Onset:
                # Artificially spike metrics for Gate_A or Gate_B when their surge ticks align
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
                    
                # 4. Standard Stadium Fluctuations:
                # Fluctuating nominal metrics based on zone types
                else:
                    if zone.startswith("Gate"):
                        # Ingress portals
                        density = 1.0 + random.uniform(-0.2, 0.2)
                        flow_in = 20.0 + random.uniform(-3, 3)
                        flow_out = 18.0 + random.uniform(-3, 3)
                    elif zone.startswith("Corridor"):
                        # Connecting tunnels
                        density = 0.8 + random.uniform(-0.15, 0.15)
                        flow_in = 18.0 + random.uniform(-3, 3)
                        flow_out = 16.0 + random.uniform(-3, 3)
                    elif zone.startswith("Transit"):
                        # Transit hub / shuttle station
                        density = 1.5 + random.uniform(-0.3, 0.3)
                        flow_in = 45.0 + random.uniform(-5, 5)
                        flow_out = 43.0 + random.uniform(-5, 5)
                    else:
                        # Large main stadium concourse
                        density = 1.2 + random.uniform(-0.2, 0.2)
                        flow_in = 36.0 + random.uniform(-5, 5)
                        flow_out = 34.0 + random.uniform(-5, 5)
                
                # Normalize values to positive bounds and clean precision decimal places
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
                
                # Sign simulated telemetry
                serialized = json.dumps(payload, sort_keys=True)
                secret = os.environ.get(
                    "TELEMETRY_SECRET_KEY", "safe-play-telemetry-secret-key-2026"
                ).encode("utf-8")
                signature = hmac.new(secret, serialized.encode("utf-8"), hashlib.sha256).hexdigest()
                payload["signature"] = signature
                
                # Push the simulated payload into the queue to run through the entire logic pipe
                orchestrator.telemetry_queue.put_nowait(json.dumps(payload))
                
        except asyncio.CancelledError:
            # Clean exit on loop cancellation
            break
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}")
