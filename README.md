# safe-play

Decentralized edge-intelligence mesh for stadium crowd safety and automated incident triage.

Processes high-frequency sensor streams through grammar-constrained local SLMs to provide real-time crowd safety recommendations with automated human-in-the-loop validation.

## Usage

Start the local telemetry broker:
```bash
mosquitto -c config/mosquitto.conf
```

Launch the local llama-server instance (optimized for prompt reuse):
```bash
./llama-server -m models/qwen-2.5-7b-instruct-q4_K_M.gguf --cache-reuse 256 -c 4096 --parallel 4
```

Execute the core asynchronous middleware engine:
```bash
python src/orchestrator.py
```

## Architecture

| Component | Description |
| --- | --- |
| **MQTT Broker** | Collects telemetry streams using dynamic QoS toggles based on zone hazard conditions. |
| **Async Middleware** | Ingests data, maps directed spatial graphs, and tracks the 2-second operator SLA window. |
| **llama-server** | Executes greedy inference under strict logit-level GBNF grammar constraints. |
| **Audit Logger** | Maintains an append-only history of inputs, schema payloads, and operational decisions. |

```text
[ESP32 Sensors] ───(QoS 0/1)───► [Mosquitto Broker]
                                         │
                                   (Async Ingest)
                                         ▼
[llama-server] ◄───(GBNF JSON)─── [Orchestrator] ───► [2s SLA Gate] ───► [Actuators/Signage]
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `MQTT_BROKER_URL` | `127.0.0.1` | Local network endpoint for the telemetry loop. |
| `INFERENCE_TIMEOUT_MS` | `100` | Prefill latency ceiling target. |
| `ACTUATION_SLA_SEC` | `2.0` | Countdown window before automated safety changes execute. |
| `FALLBACK_DENSITY_LIMIT` | `3.0` | People/$m^2$ trigger point for rule-based overrides. |

## Testing

Execute the localized validation suites:
```bash
pytest tests/test_schemas.py
pytest tests/test_fallbacks.py
```
