"""
Configuration and Initialization Settings for SafePlay.

Role:
    Initializes system-wide logging, parses local environment variables from `.env`
    into process environments (`os.environ`), and defines central configuration constants
    governing system timeouts, fallback triggers, and file paths.

Ecosystem Positioning:
    - Root-level configuration provider.
    - Exported constants (such as ACTUATION_SLA_SEC, FALLBACK_DENSITY_LIMIT, and AUDIT_LOG_FILE)
      are imported by:
        - `src/orchestrator.py`: to govern operator veto durations and safety density boundaries.
        - `src/audit.py`: to locate the append-only JSONL cryptographic ledger path.
        - `src/web_api.py`: to manage server endpoints, CORS permissions, and override configs.
        - `src/inference.py`: to set timeout boundaries on LLM engine requests.
"""


import os
import logging
import sys

def load_env() -> None:
    """
    Parses a local .env configuration file if it exists and populates os.environ.
    Allows local developer configurations to override system defaults without mutating
    production environments.
    """
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                # Skip empty lines, comments, or malformed entries
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    # Strip quoting characters from parsed environment values
                    val = val.strip().strip('"').strip("'")
                    # Do not overwrite existing environment variables
                    if key and key not in os.environ:
                        os.environ[key] = val

# Run environment initialization immediately on import
load_env()

# Configure uniform logging to standard output for container/cloud logging compliance
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Orchestrator")

# ---------------------------------------------------------------------------
# System Constants
# ---------------------------------------------------------------------------

# Default address of the MQTT message broker used for IoT telemetry ingestion
DEFAULT_BROKER = "127.0.0.1"

# Default port of the MQTT message broker
DEFAULT_PORT = 1883

# Path to the JSON schema defining structural constraints for the LLM output
DEFAULT_SCHEMA_PATH = "config/schema.json"

# Strict timeout boundary for local LLM inference calls to maintain real-time SLA (100ms)
INFERENCE_TIMEOUT_SEC = 0.1

# Fallback threshold (people/m^2). Over this, fallback safety overrides are enforced.
FALLBACK_DENSITY_LIMIT = 3.0

# Actuation SLA safety window (seconds). Time given to operators to veto actions.
ACTUATION_SLA_SEC = 15.0

# Persistent output file path for append-only audit trail logging
AUDIT_LOG_FILE = "logs/audit_trail.jsonl"
