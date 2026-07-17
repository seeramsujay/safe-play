"""
Inference Module for SafePlay Crowd Safety Orchestrator.

This module provides functions to query either remote Google Gemini APIs (with native
JSON Schema output enforcement) or a local llama-server completions endpoint (with GBNF grammar
enforcement). If the model inference fails, times out, or becomes unavailable, it falls back to
a local, deterministic rule-based safety recommendation.
"""

import os
import json
import time
import httpx
from typing import Optional
from src.models import TelemetryPayload, InterventionScript
from src.config import INFERENCE_TIMEOUT_SEC, logger

async def get_slm_recommendation(orchestrator, payload: TelemetryPayload) -> Optional[InterventionScript]:
    """
    Queries the configured LLM/SLM engine under strict structural constraints to
    obtain crowd management recommendations.
    
    If GEMINI_API_KEY is found in the environment, this method calls the Google Gemini REST API.
    Otherwise, it defaults to a local llama-server instance running on port 8080.
    
    Args:
        orchestrator: The orchestrator instance managing system configurations, clients, and graph states.
        payload: TelemetryPayload instance containing current crowd density and flow metrics.
        
    Returns:
        A validated InterventionScript instance containing safety instructions, or
        None if the inference request fails, raises an exception, or times out.
    """
    # Look up alternative routing options via cython/python graph traversal
    alt_route = orchestrator.graph.get_alternative_route(payload.zone_id)
    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    
    if gemini_api_key:
        # Remote Gemini REST endpoint utilizing developer-supplied API key
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_api_key}"
        
        # Zero-shot prompt providing structural context for inference
        prompt = (
            f"STAD_ZONE: {payload.zone_id}\n"
            f"DENSITY: {payload.crowd_density:.2f}\n"
            f"FLOW_IN: {payload.flow_rate_in:.2f}\n"
            f"FLOW_OUT: {payload.flow_rate_out:.2f}\n"
            f"ALT_ROUTE: {alt_route or 'NONE'}\n\n"
            f"Assess crowd hazard for FIFA World Cup 2026. Recommend turnstile gate action, multilingual signage/audio instructions in English, Spanish, and French, special ADA accessibility redirection targets/notes, and transit coordination instructions. "
            f"Generate a valid JSON object matching the InterventionScript schema."
        )
        
        # Enforce exact JSON response schema using Gemini's native schema constraints
        req_payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "zone_id": {
                            "type": "STRING",
                            "description": "Must match STAD_ZONE exactly"
                        },
                        "hazard_level": {
                            "type": "STRING",
                            "enum": ["low", "medium", "high", "critical"]
                        },
                        "action_required": {
                            "type": "BOOLEAN"
                        },
                        "reroute_target": {
                            "type": "STRING",
                            "description": "Alternative zone_id to redirect crowd flow or null"
                        },
                        "signage_instruction_en": {
                            "type": "STRING",
                            "description": "English signage message (max 120 chars)"
                        },
                        "signage_instruction_es": {
                            "type": "STRING",
                            "description": "Spanish signage message translation (max 120 chars)"
                        },
                        "signage_instruction_fr": {
                            "type": "STRING",
                            "description": "French signage message translation (max 120 chars)"
                        },
                        "audio_announcement_en": {
                            "type": "STRING",
                            "description": "English PA announcement audio transcript (max 200 chars)"
                        },
                        "audio_announcement_es": {
                            "type": "STRING",
                            "description": "Spanish PA announcement audio transcript (max 200 chars)"
                        },
                        "audio_announcement_fr": {
                            "type": "STRING",
                            "description": "French PA announcement audio transcript (max 200 chars)"
                        },
                        "gate_action": {
                            "type": "STRING",
                            "enum": ["KEEP_OPEN", "SLOW_ENTRY", "CLOSE_IMMEDIATELY", "REVERSE_FLOW"]
                        },
                        "accessibility_route_target": {
                            "type": "STRING",
                            "description": "Optional alternative ADA zone ID (like Gate_C) or null"
                        },
                        "accessibility_instruction": {
                            "type": "STRING",
                            "description": "Special ADA guidelines or null"
                        },
                        "transit_dispatch_action": {
                            "type": "STRING",
                            "enum": ["KEEP_NOMINAL", "INCREASE_SHUTTLE_FREQUENCY", "REDIRECT_METRO_PASSENGER_ENTRY", "HOLD_METRO_TRAINS"]
                        },
                        "transit_instruction": {
                            "type": "STRING",
                            "description": "Transit operational guidelines"
                        },
                        "rationale": {
                            "type": "STRING",
                            "description": "Zero-fluff explanation of the assessment (maximum 10 words)"
                        }
                    },
                    "required": [
                        "zone_id", "hazard_level", "action_required", 
                        "signage_instruction_en", "signage_instruction_es", "signage_instruction_fr", 
                        "audio_announcement_en", "audio_announcement_es", "audio_announcement_fr", 
                        "gate_action", "transit_dispatch_action", "transit_instruction", "rationale"
                    ]
                }
            }
        }
        # Allow up to 2.0 seconds for external cloud API round-trips
        timeout = httpx.Timeout(2.0, connect=1.0)
    else:
        # Local llama-server endpoint using GBNF JSON schemas
        url = os.environ.get("LLAMA_SERVER_URL", "http://localhost:8080/completion")
        
        prompt = (
            f"STAD_ZONE: {payload.zone_id}\n"
            f"DENSITY: {payload.crowd_density:.2f}\n"
            f"FLOW_IN: {payload.flow_rate_in:.2f}\n"
            f"FLOW_OUT: {payload.flow_rate_out:.2f}\n"
            f"ALT_ROUTE: {alt_route or 'NONE'}\n"
            f"Assess crowd hazard for FIFA World Cup 2026. Recommend turnstile gate action, multilingual signage/audio (EN, ES, FR), accessibility ADA route targets, and transit coordination."
        )
        
        req_payload = {
            "prompt": prompt,
            "temperature": 0.0,
            "stream": False,
            "n_predict": 256,
            "json_schema": orchestrator.json_schema,
            "stop": ["\n\n"],
        }
        # Enforce sub-100ms real-time latency boundary for local edge servers
        timeout = httpx.Timeout(INFERENCE_TIMEOUT_SEC, connect=1.0)
        
    start_time = time.time()
    try:
        # Submit POST request to the inference server
        response = await orchestrator.http_client.post(url, json=req_payload, timeout=timeout)
        latency_ms = (time.time() - start_time) * 1000.0
        
        if response.status_code == 200:
            resp_json = response.json()
            
            # Extract content payload based on the response format of the active model engine
            if gemini_api_key:
                candidates = resp_json.get("candidates", [])
                if candidates:
                    text_content = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                    parsed_content = json.loads(text_content)
                else:
                    raise ValueError("No candidates returned from Gemini API response.")
            else:
                content = resp_json.get("content", "").strip()
                parsed_content = json.loads(content)
            
            # Normalize empty strings back to None for standardized routing targets
            if parsed_content.get("reroute_target") == "":
                parsed_content["reroute_target"] = None
            if parsed_content.get("accessibility_route_target") == "":
                parsed_content["accessibility_route_target"] = None
            if parsed_content.get("accessibility_instruction") == "":
                parsed_content["accessibility_instruction"] = None
            
            # Validate output structurally using our Pydantic model
            script = InterventionScript.model_validate(parsed_content)
            
            # Record telemetry stats on orchestrator instance for status dashboard reporting
            orchestrator.last_llm_latency_ms = latency_ms
            orchestrator.last_llm_status = True
            
            # Write a persistent entry to the security audit trail
            orchestrator.write_audit_log("inference_success", {
                "zone_id": payload.zone_id,
                "latency_ms": latency_ms,
                "engine": "gemini" if gemini_api_key else "llama",
                "response": parsed_content
            })
            return script
        else:
            logger.error(f"Inference server error: {response.status_code} {response.text}")
            orchestrator.last_llm_latency_ms = latency_ms
            orchestrator.last_llm_status = False
            
    except (httpx.TimeoutException, httpx.RequestError, json.JSONDecodeError, Exception) as e:
        latency_ms = (time.time() - start_time) * 1000.0
        logger.warning(f"Inference engine unavailable or timed out ({latency_ms:.1f}ms). Reason: {type(e).__name__}")
        
        orchestrator.last_llm_latency_ms = latency_ms
        orchestrator.last_llm_status = False
        
        # Log the inference fallback event to the audit trail for regulatory traceability
        orchestrator.write_audit_log("inference_fallback", {
            "zone_id": payload.zone_id,
            "latency_ms": latency_ms,
            "error": str(e)
        })
        
    return None

def get_static_fallback_recommendation(orchestrator, payload: TelemetryPayload) -> InterventionScript:
    """
    Rule-based deterministic backup system that executes immediately when the LLM is offline or times out.
    Guarantees that safety recommendations can be made within sub-millisecond timelines.
    
    Args:
        orchestrator: The active orchestrator instance.
        payload: TelemetryPayload containing crowd flow and density values.
        
    Returns:
        An InterventionScript generated using static safety rules.
    """
    alt_route = orchestrator.graph.get_alternative_route(payload.zone_id)
    
    # Critical state: Crowd density is at or above the safety limit
    if payload.crowd_density >= orchestrator.fallback_density_limit:
        ada_route = "Gate_C" if payload.zone_id in ("Gate_A", "Gate_B") else None
        return InterventionScript(
            zone_id=payload.zone_id,
            hazard_level="critical",
            action_required=True,
            reroute_target=alt_route,
            signage_instruction_en=f"CRITICAL OVERLOAD. USE ROUTE {alt_route or 'NEAREST EXIT'}",
            signage_instruction_es=f"SOBRECARGA CRÍTICA. USE LA RUTA {alt_route or 'SALIDA MÁS CERCANA'}",
            signage_instruction_fr=f"SURCHARGE CRITIQUE. UTILISEZ LA ROUTE {alt_route or 'SORTIE LA PLUS PROCHE'}",
            audio_announcement_en="Attention please: this portal is temporarily closed due to congestion. Please follow the illuminated green ADA arrows to the nearest exit.",
            audio_announcement_es="Atención por favor: este portal está temporalmente cerrado debido a la congestión. Siga las flechas verdes ADA hacia la salida más cercana.",
            audio_announcement_fr="Attention s'il vous plaît: ce portail est temporairement fermé en raison de la congestion. Veuillez suivre les flèches vertes ADA vers la sortie la plus proche.",
            gate_action="CLOSE_IMMEDIATELY",
            accessibility_route_target=ada_route,
            accessibility_instruction="Stroller and wheelchair traffic redirect to North Portal Gate C.",
            transit_dispatch_action="INCREASE_SHUTTLE_FREQUENCY",
            transit_instruction="Request immediate transit frequency increase to disperse outbound crowds.",
            rationale="Fallback: density limit exceeded"
        )
    # Elevated state: Moderate density, slow down entry but keep flow moving
    else:
        return InterventionScript(
            zone_id=payload.zone_id,
            hazard_level="medium",
            action_required=False,
            reroute_target=None,
            signage_instruction_en="PLEASE KEEP MOVING",
            signage_instruction_es="POR FAVOR MANTÉNGASE EN MOVIMIENTO",
            signage_instruction_fr="VEUILLEZ CONTINUER À AVANCER",
            audio_announcement_en="Please continue moving through the corridor towards the main festival plaza.",
            audio_announcement_es="Continúe moviéndose por el corredor hacia la plaza principal del festival.",
            audio_announcement_fr="Veuillez continuer à vous déplacer dans le couloir vers la place principale du festival.",
            gate_action="SLOW_ENTRY",
            accessibility_route_target=None,
            accessibility_instruction="ADA routing lanes are nominal and fully clear.",
            transit_dispatch_action="KEEP_NOMINAL",
            transit_instruction="Maintain nominal transit operations and gate flow monitoring.",
            rationale="Fallback: density elevated"
        )
