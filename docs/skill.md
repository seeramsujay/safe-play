# Skill: Configure and Execute Grammar-Constrained Inference with Human-in-the-Loop Validation

## When to use
Use when updating the Pydantic schemas, modifying GBNF grammars, or testing the edge decision pipeline's response to telemetry anomalies.

## Prerequisites
* Local Mosquitto MQTT broker running on `localhost:1883`.
* Access to a Google Colab instance for heavy telemetry generation or load testing.
* Quantized `Qwen-2.5-7B-Instruct-q4_K_M.gguf` file downloaded.

## Steps
1. Start the local `llama-server` on the orchestration machine with prompt caching enabled:
```bash
./llama-server -m qwen-2.5-7B-instruct-q4_K_M.gguf -c 4096 --port 8080 --parallel 4 --cache-reuse 256 --no-kv-unified
```

2. Verify the server is live and responsive by querying the health endpoint:
```bash
curl http://localhost:8080/health
```

3. Open the target Google Colab notebook to compile the GBNF grammar state machine from the raw Pydantic JSON schema using the following notebook structure:
```python
# Colab Cell: Environment Setup & Schema Compilation
!pip install pydantic outlines httpx
import json
from pydantic import BaseModel

# Mount Google Drive to preserve outputs
from google.colab import drive
drive.mount('/content/drive')

# Compile and export schema
# [Execute schema generation and save json to /content/drive/MyDrive/safe-play/schema.json]
```

4. Copy the compiled schema artifact from Google Drive into the local project folder under `config/schema.json`.

5. Compile the Cython-optimized C extension routing module locally to ensure sub-millisecond computations:
```bash
uv run python setup.py build_ext --inplace
```

6. Start the async Python orchestrator middleware script inside the virtual environment:
```bash
uv run python -m src.orchestrator
```

7. Simulate an anomalous telemetry payload ($>3.0 \text{ people/m}^2$) via a lightweight local curl request or MQTT pub call to trigger the Human-In-The-Loop (HITL) 2-second SLA timer window.

8. Verify the local validation suite runs and passes successfully:
```bash
uv run pytest
```

## Output
A successful execution yields an append-only audit trail log entry containing the exact JSON model response, a calculated end-to-end latency metric, and the status of the operator's confirmation or veto signal.

## Failure modes
* **VRAM Contention / Token Crawl**: Llama-server response times drop below the sub-second threshold. Fix: Reduce the `--parallel` slots down to `2` and ensure `--no-kv-unified` is passed to guarantee unpageable context per slot.
* **JSON Schema Discrepancy**: The Pydantic validator throws a validation exception on client ingestion. Fix: Verify `additionalProperties: False` is explicitly declared in the JSON schema object compiled on Colab.
* **Missing Cython Compiled Modules**: Cython routing fallback flags system status as using unoptimized modules. Fix: Compile the module with `uv run python` before starting the dashboard.
