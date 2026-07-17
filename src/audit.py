"""
Audit Trail Logging Module for SafePlay.

This module handles writing structured, append-only security logs of critical 
system state transitions, such as incident alerts, operator overrides (vetos/approvals),
and configuration changes, to a persistent JSON Lines (JSONL) format.
Each entry is cryptographically linked to the previous entry to prevent tampering.
"""

import os
import json
import time
import hashlib
from src.config import AUDIT_LOG_FILE, logger

def get_last_audit_hash() -> str:
    """
    Efficiently retrieves the hash of the last log entry by seeking to the end 
    of the file and reading the last line. O(1) memory and time complexity.
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return "0" * 64
    try:
        with open(AUDIT_LOG_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            file_size = f.tell()
            if file_size == 0:
                return "0" * 64
                
            # Seek backwards a bit from the end (up to 4096 bytes is safe for a single line)
            buffer_size = min(4096, file_size)
            f.seek(-buffer_size, os.SEEK_END)
            chunk = f.read(buffer_size)
            
            # Find the last line in the chunk
            lines = chunk.split(b"\n")
            # The last element might be empty if the file ends with a newline
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        last_entry = json.loads(line.decode("utf-8"))
                        if "hash" in last_entry:
                            return last_entry["hash"]
                    except json.JSONDecodeError:
                        pass
    except Exception as e:
        logger.error(f"Error reading last audit log hash: {e}")
    return "0" * 64

def write_audit_log(log_type: str, data: dict) -> None:
    """
    Appends an audit trail record to a persistent JSON Lines (.jsonl) file.
    Each log entry is cryptographically chained to the previous line's hash
    to ensure tamper-evident logging history.
    
    Args:
        log_type: String identifier of the type of event (e.g. 'operator_veto', 'config_update').
        data: Key-value dictionary containing contextual parameters/attributes of the event.
    """
    # Extract the directory portion of the audit path (defaults to current directory if not specified)
    log_dir = os.path.dirname(AUDIT_LOG_FILE) or "."
    
    # Ensure the logs directory is created in a race-free manner
    os.makedirs(log_dir, exist_ok=True)
    
    # Determine the hash of the last entry in the file to create the chain link
    prev_hash = get_last_audit_hash()
            
    # Construct a structured log entry with precise epoch timestamp
    log_entry = {
        "timestamp": time.time(),
        "event_type": log_type,
        "prev_hash": prev_hash,
        **data
    }
    
    # Serialize to deterministic JSON string (sorted keys) to compute stable SHA-256
    serialized = json.dumps(log_entry, sort_keys=True)
    current_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    log_entry["hash"] = current_hash
    
    # Write in append mode to satisfy write-once-read-many (WORM) audit safety principles
    with open(AUDIT_LOG_FILE, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
        
    # Log information statement to the application logger console
    logger.info(f"Audit Trail Written [{log_type}]: {data.get('zone_id', 'global')}")


def verify_audit_trail() -> bool:
    """
    Validates the integrity of the audit log file by checking the hash chain.
    Returns True if the chain is unbroken and untampered, False otherwise.
    """
    if not os.path.exists(AUDIT_LOG_FILE):
        return True
    try:
        expected_prev_hash = "0" * 64
        with open(AUDIT_LOG_FILE, "r") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                
                # Check for cryptographic fields
                if "hash" not in entry or "prev_hash" not in entry:
                    logger.error(f"Audit log line {line_num} missing cryptographic metadata.")
                    return False
                    
                # Validate the chain link to the previous entry
                if entry["prev_hash"] != expected_prev_hash:
                    logger.error(
                        f"Audit log chain broken at line {line_num}! "
                        f"Expected prev_hash: {expected_prev_hash}, found: {entry['prev_hash']}"
                    )
                    return False
                    
                # Verify the current entry's hash integrity
                entry_hash = entry["hash"]
                entry_copy = dict(entry)
                entry_copy.pop("hash")
                
                serialized = json.dumps(entry_copy, sort_keys=True)
                computed_hash = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
                
                if entry_hash != computed_hash:
                    logger.error(f"Audit log tamper detected at line {line_num}! Hash verification failed.")
                    return False
                    
                expected_prev_hash = entry_hash
        return True
    except Exception as e:
        logger.error(f"Error validating audit trail: {e}")
        return False

