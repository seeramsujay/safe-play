"""
Pytest configuration and global mocking fixtures for SafePlay.

Role:
    Configures the testing environment by defining shareable fixtures, overrides,
    and a global monkeypatch/interceptor on `httpx.AsyncClient.send`. This prevents
    tests from sending outbound network requests to Google Gemini or a local llama-server,
    providing deterministic mock JSON structures representing safety recommendations instead.

Ecosystem Positioning:
    - Below: Pytest runner library.
    - Above: Auto-discovered and loaded by pytest prior to executing test cases in:
      - `tests/test_end_to_end.py`
      - `tests/test_extensive_scenarios.py`
      - `tests/test_fallbacks.py`
      - `tests/test_mqtt.py`
      - `tests/test_schemas.py`
      - `tests/test_web_api.py`
"""

import pytest
import asyncio
import json
import httpx
from unittest.mock import patch
from src.orchestrator import SafePlayOrchestrator

# --- Global HTTPX Async Client Mocking to Prevent External Sockets ---
original_send = httpx.AsyncClient.send

async def patched_send(self, request, *args, **kwargs):
    host = request.url.host
    if host and ("generativelanguage.googleapis.com" in host or (host == "127.0.0.1" and request.url.port == 8080)):
        req_content = request.content.decode("utf-8", errors="ignore")
        
        # Determine if it's Copilot or SLM
        is_copilot = "generationConfig" in req_content and "responseSchema" in req_content and "answer" in req_content
        
        if is_copilot:
            # Check prompt for keywords to return realistic mocked answers matching tests
            prompt_text = ""
            try:
                req_json = json.loads(req_content)
                text = req_json["contents"][0]["parts"][0]["text"]
                if "Operator Query:" in text:
                    prompt_text = text.split("Operator Query:")[-1].lower()
                else:
                    prompt_text = text.lower()
            except Exception:
                pass
            
            ans = "Command Center Copilot: I am online monitoring the stadium spatial graph."
            if "transit" in prompt_text or "metro" in prompt_text or "bus" in prompt_text or "shuttle" in prompt_text:
                ans = "Transit Coordination: Outbound dispersal is routed through public transit hubs."
            elif "accessibility" in prompt_text or "wheelchair" in prompt_text or "ada" in prompt_text or "ramp" in prompt_text:
                ans = "Accessibility Protocol: Under current World Cup stadium configurations, Gate C and the Accessibility Ramp are designated as ADA egress routes."
            elif "language" in prompt_text or "spanish" in prompt_text or "french" in prompt_text:
                ans = "Multilingual Support: EdgePulse dynamically broadcasts all safety alerts in English, Spanish, and French concurrently."
                
            mock_data = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({"answer": ans})
                        }]
                    }
                }]
            }
            content = json.dumps(mock_data).encode("utf-8")
        else:
            # It's an SLM recommendation request
            zone_id = "Gate_A"
            for z in ["Gate_A", "Gate_B", "Gate_C", "Corridor_1", "Corridor_2", "Main_Concourse"]:
                if z in req_content:
                    zone_id = z
                    break
            
            slm_mock_response = {
                "zone_id": zone_id,
                "hazard_level": "critical",
                "action_required": True,
                "reroute_target": "Corridor_2" if zone_id == "Gate_A" else "Main_Concourse",
                "signage_instruction_en": f"USE ALTERNATIVE PATH FOR {zone_id.replace('_', ' ')}",
                "signage_instruction_es": f"USE CORREDOR ALTERNATIVO PARA {zone_id.replace('_', ' ')}",
                "signage_instruction_fr": f"UTILISER LE PATH ALTERNATIF POUR {zone_id.replace('_', ' ')}",
                "audio_announcement_en": f"Please use alternative path for {zone_id.replace('_', ' ')}",
                "audio_announcement_es": "Por favor use el camino alternativo",
                "audio_announcement_fr": "S'il vous plaît utiliser le chemin alternatif",
                "gate_action": "CLOSE_IMMEDIATELY",
                "accessibility_route_target": "Corridor_2_ADA",
                "accessibility_instruction": "Use ADA-compliant ramp",
                "transit_dispatch_action": "INCREASE_SHUTTLE_FREQUENCY",
                "transit_instruction": "Dispatch additional transit resources",
                "rationale": f"High density surge detected in {zone_id}"
            }
            
            if "generativelanguage.googleapis.com" in host:
                mock_data = {
                    "candidates": [{
                        "content": {
                            "parts": [{
                                "text": json.dumps(slm_mock_response)
                            }]
                        }
                    }]
                }
            else:
                # llama-server format
                mock_data = {
                    "content": json.dumps(slm_mock_response)
                }
            content = json.dumps(mock_data).encode("utf-8")
            
        return httpx.Response(
            status_code=200,
            content=content,
            request=request
        )
        
    return await original_send(self, request, *args, **kwargs)

httpx.AsyncClient.send = patched_send

# --- Track SafePlayOrchestrator instances for teardown ---
_orchestrator_instances = []

original_init = SafePlayOrchestrator.__init__

def patched_init(self, *args, **kwargs):
    original_init(self, *args, **kwargs)
    _orchestrator_instances.append(self)

SafePlayOrchestrator.__init__ = patched_init

@pytest.fixture(autouse=True)
def cleanup_orchestrator_clients():
    """
    Autouse fixture that registers all created SafePlayOrchestrator instances during a test,
    and guarantees their underlying HTTP/HTTPX clients are closed to prevent ResourceWarnings
    about unclosed sockets and event loop leaks.
    """
    _orchestrator_instances.clear()
    yield
    for inst in list(_orchestrator_instances):
        try:
            # Cancel any remaining background intervention tasks to avoid leaks
            for zone_id, task in list(inst.active_interventions.items()):
                if not task.done():
                    task.cancel()
            
            # Cleanly close the HTTP client if initialized
            if hasattr(inst, "_http_client") and not inst._http_client.is_closed:
                loop = None
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    pass
                
                if loop and loop.is_running():
                    # Schedule asynchronous closure within the running event loop
                    loop.create_task(inst._http_client.aclose())
                else:
                    # Run synchronous/blocking closure if no event loop is active
                    asyncio.run(inst._http_client.aclose())
        except Exception:
            pass
    _orchestrator_instances.clear()
