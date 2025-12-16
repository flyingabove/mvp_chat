import json
import os
from datetime import datetime
from typing import Any, Dict, Optional


def _enabled() -> bool:
    return os.getenv("REQUEST_LOGGING", "1") == "1"


def log_event(
    request_id: str,
    stage: str,
    payload: Dict[str, Any],
    *,
    level: str = "INFO",
):
    """
    Logs a single JSON event.
    IMPORTANT: prints to STDOUT so Railway captures it in Deploy/Service Logs.
    """
    if not _enabled():
        return

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "level": level,
        "request_id": request_id,
        "stage": stage,
        "payload": payload,
    }

    # STDOUT is the correct sink for Railway app logs
    print(json.dumps(record, ensure_ascii=False))
