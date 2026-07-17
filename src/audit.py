"""
Audit Trail Logging Module for SafePlay.

This module handles writing structured, append-only security logs of critical 
system state transitions, such as incident alerts, operator overrides (vetos/approvals),
and configuration changes, to a persistent JSON Lines (JSONL) format.
"""

import os
import json
import time
from src.config import AUDIT_LOG_FILE, logger

def write_audit_log(log_type: str, data: dict) -> None:
    """
    Appends an audit trail record to a persistent JSON Lines (.jsonl) file.
    Automatically ensures that the destination directory exists before writing.
    
    Args:
        log_type: String identifier of the type of event (e.g. 'operator_veto', 'config_update').
        data: Key-value dictionary containing contextual parameters/attributes of the event.
    """
    # Extract the directory portion of the audit path (defaults to current directory if not specified)
    log_dir = os.path.dirname(AUDIT_LOG_FILE) or "."
    
    # Ensure the logs directory is created in a race-free manner
    os.makedirs(log_dir, exist_ok=True)
    
    # Construct a structured log entry with precise epoch timestamp
    log_entry = {
        "timestamp": time.time(),
        "event_type": log_type,
        **data
    }
    
    # Write in append mode to satisfy write-once-read-many (WORM) audit safety principles
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
        
    # Log information statement to the application logger console
    logger.info(f"Audit Trail Written [{log_type}]: {data.get('zone_id', 'global')}")
