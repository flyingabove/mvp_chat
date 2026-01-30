# backend/app/utils/logging_utils.py
"""
Shared logging utilities for Railway deploy logs.
Consolidates JSON logging and truncation helpers used across the codebase.
"""

import json
import time


def jlog(event: dict) -> None:
    """
    JSON-line logging to stdout. Shows up in Railway Deploy Logs.
    Adds a timestamp automatically if not present.
    """
    try:
        obj = dict(event)
        obj.setdefault("ts", time.time())
        print(json.dumps(obj, ensure_ascii=False))
    except Exception:
        pass


def truncate(s: str, n: int = 500, suffix: str = "...") -> str:
    """
    Truncate a string to at most n characters.

    Args:
        s: The string to truncate
        n: Maximum length (default 500)
        suffix: What to append when truncated (default "...")

    Returns:
        Truncated string with suffix if it was truncated
    """
    if s is None:
        return ""
    s = str(s)
    if len(s) <= n:
        return s
    return s[:n - len(suffix)] + suffix
