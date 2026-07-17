"""
GenAI Stadium Operations Copilot Module for FIFA World Cup 2026.

This module provides real-time decision support for stadium operations commanders,
volunteers, and transit coordinators by combining current telemetry, spatial graph routes,
and official FIFA 2026 safety SOPs via Generative AI or fallback semantic heuristics.
"""

import os
import json
import time
import httpx
from typing import Optional, List, Dict, Any
from src.models import CopilotRequest, CopilotResponse
from src.config import logger

# Static FIFA World Cup 2026 Command Center SOPs
FIFA_2026_SOPS = """
FIFA WORLD CUP 2026 - VENUE COMMAND & EGRESS OPERATIONS SOPS:
1. Crowd Safety & Egress Control:
   - Normal operating threshold: Density < 1.5 people/m^2.
   - Elevated Warning threshold: Density >= 1.5 and < 2.0 people/m^2. Requires SLOW_ENTRY and monitoring.
   - Critical Overload: Density >= 2.0 people/m^2 (or dynamic fallback_density_limit). Requires immediate Gate CLOSE_IMMEDIATELY action and rerouting to alternative egress target zones.
   - Spatial routing uses a directed graph to find adjacent nodes with maximum spare capacity.

2. Multilingual Information Policy:
   - All dynamic electronic signage and public address (PA) audio broadcasts must run in English, Spanish, and French concurrently.
   - Signage messages must be brief (max 120 chars); audio announcements must be clear transcripts (max 200 chars).

3. Accessibility & ADA Egress Protocol:
   - Accessibility Ramp North and Gate C are the primary ADA-compliant egress paths.
   - Under heavy crowd surges at Gate A (East) or Gate B (West), redirect all strollers, wheelchairs, and mobility-assisted patrons to Gate C (North Portal).

4. Transit Hub Coordination Protocol:
   - Outbound crowd dispersals must coordinate with Transit Hub Metro and Transit Hub Shuttle Bus.
   - Action 'INCREASE_SHUTTLE_FREQUENCY': Dispatch additional buses to clear Gate vomitories.
   - Action 'REDIRECT_METRO_PASSENGER_ENTRY': Divert crowds away from metro stations to avoid platform crush.
   - Action 'HOLD_METRO_TRAINS': Hold inbound/outbound transit during active gate evacuations.
"""

async def query_copilot(orchestrator, request: CopilotRequest) -> CopilotResponse:
    """
    Processes an operator query using Gemini's structured generation capabilities
    or a localized semantic fallback engine.
    
    Args:
        orchestrator: The active orchestrator instance.
        request: The CopilotRequest containing the query text and target zone.
        
    Returns:
        A CopilotResponse containing the natural language answer and system states.
    """
    start_time = time.time()
    
    # 1. Gather current stadium status for prompt context
    nodes_info = []
    active_incidents = 0
    overloaded_zones = []
    
    for zone_id, node in orchestrator.graph.nodes.items():
        density = node.current_density
        capacity = node.capacity
        is_overloaded = density >= capacity
        
        # Count incident if zone density exceeds dynamic safety threshold or active intervention is pending
        active_script = orchestrator.active_scripts.get(zone_id)
        has_active_script = active_script is not None
        
        if is_overloaded or has_active_script:
            active_incidents += 1
            if is_overloaded:
                overloaded_zones.append(zone_id)
                
        nodes_info.append({
            "zone_id": zone_id,
            "current_density": round(density, 2),
            "max_capacity": capacity,
            "status": "CRITICAL" if is_overloaded else ("WARNING" if density >= 1.5 else "NOMINAL"),
            "active_intervention": active_script.gate_action if active_script else None
        })
        
    # Generate static hazard summary
    if len(overloaded_zones) > 0:
        hazard_summary = f"CRITICAL overload in progress at: {', '.join(overloaded_zones)}. Active response protocols actuated."
    elif active_incidents > 0:
        hazard_summary = f"{active_incidents} zones under warning/active operator review. Monitoring flow rates."
    else:
        hazard_summary = "All gates and concourses reporting nominal crowd densities and transit flows."

    # 2. Check for Gemini API key to run GenAI pipeline
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if gemini_api_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
        
        # Build prompt containing full context
        system_context = (
            f"You are the FIFA World Cup 2026 Stadium Operations Copilot. "
            f"You assist stadium command coordinators using the following standard operating procedures:\n"
            f"{FIFA_2026_SOPS}\n\n"
            f"--- LIVE VENUE TELEMETRY STATE ---\n"
            f"Active Incident Count: {active_incidents}\n"
            f"Dynamic Fallback Density Limit: {orchestrator.fallback_density_limit:.2f} people/m^2\n"
            f"Zone Status Details:\n{json.dumps(nodes_info, indent=2)}\n"
            f"Panic Mode: {'ACTIVE - ALL EXIT GATES FORCED OPEN' if orchestrator.panic_mode else 'INACTIVE'}\n"
            f"Operator Veto Countdown SLA Window: {orchestrator.actuation_sla_sec} seconds\n\n"
            f"Answer the operator's query accurately using the telemetry data and SOPs above. "
            f"If the question refers to a specific zone, focus on that zone's metrics and transit connectivity."
        )
        
        req_payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_context}\n\nOperator Query: {request.prompt}"}]}
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "answer": {
                            "type": "STRING",
                            "description": "Natural language answer, clear, concise, professional (max 150 words)."
                        }
                    },
                    "required": ["answer"]
                }
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=req_payload, timeout=5.0)
                if response.status_code == 200:
                    resp_json = response.json()
                    candidates = resp_json.get("candidates", [])
                    if candidates:
                        text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                        parsed = json.loads(text_content)
                        return CopilotResponse(
                            answer=parsed.get("answer", "No answer field found in response."),
                            timestamp=time.time(),
                            active_incident_count=active_incidents,
                            hazard_summary=hazard_summary
                        )
        except Exception as e:
            logger.warning(f"Copilot Gemini API query failed, falling back to local heuristic: {e}")

    # 3. Fallback Heuristic Matcher (runs offline or on API failure)
    query_lower = request.prompt.lower()
    
    # ADA / Accessibility queries
    if any(k in query_lower for k in ["ada", "wheelchair", "stroller", "accessibility", "disabled", "ramp"]):
        answer = (
            "Accessibility Protocol: Under current World Cup stadium configurations, "
            "Gate C (North Portal) and the Accessibility Ramp North are designated as ADA egress routes. "
            "If Gate A (East) or Gate B (West) experience congestion, dynamic signage will route ADA guests to Gate C. "
            f"Current state: Gate C density is {orchestrator.graph.nodes['Gate_C_North_ADA'].current_density:.1f} people/m^2 (nominal)."
        )
    # Transit / Shuttle / Metro queries
    elif any(k in query_lower for k in ["transit", "metro", "bus", "shuttle", "transport", "train"]):
        outbound_zones = []
        for zone in ["Transit_Hub_Metro", "Transit_Hub_Shuttle_Bus"]:
            outbound_zones.append(f"{zone} (Density: {orchestrator.graph.nodes[zone].current_density:.1f}/m^2)")
        
        answer = (
            "Transit Coordination: Outbound dispersal is routed through public transit hubs. "
            "If major exits overflow, dispatch commands request increased bus frequencies or train entry holds. "
            f"Current hub statuses: {', '.join(outbound_zones)}. "
            "Transit dispatch recommendation will match flow demand to prevent station congestion."
        )
    # Language / Spanish / French queries
    elif any(k in query_lower for k in ["language", "spanish", "french", "espanol", "francais", "translate", "translation"]):
        answer = (
            "Multilingual Support: EdgePulse dynamically broadcasts all safety alerts in English, Spanish, "
            "and French concurrently. Visual digital displays render three languages in rotation, "
            "and public address audio tracks are queued in all three languages to guide international visitors safely."
        )
    # Density / Overload / Incident status queries
    elif any(k in query_lower for k in ["density", "incident", "hazard", "threat", "status", "safe", "overload", "clogged"]):
        if len(overloaded_zones) > 0:
            answer = (
                f"Active Incident Alert: {len(overloaded_zones)} vomitory portals exceed safe density limits: "
                f"{', '.join(overloaded_zones)}. Signage and gate controls have been triggered to reroute fans. "
                "Recommend deploying physical marshals to guide flow."
            )
        else:
            answer = (
                f"Stadium Status Nominal: No zones currently exceed density thresholds. "
                f"Active incidents: {active_incidents}. General operations are running smoothly."
            )
    # Default operations assistant greeting
    else:
        answer = (
            "Command Center Copilot: I am online monitoring the stadium spatial graph. "
            f"Currently tracking {len(orchestrator.graph.nodes)} nodes. Active incidents: {active_incidents}. "
            "Ask me about accessibility routing, transit dispatch directives, translation templates, "
            "or specific vomitory densities to support your decisions."
        )

    return CopilotResponse(
        answer=answer,
        timestamp=time.time(),
        active_incident_count=active_incidents,
        hazard_summary=hazard_summary
    )
