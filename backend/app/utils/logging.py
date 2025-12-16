import json, time

def jlog(event: dict):
    event = dict(event)
    event.setdefault("ts_ms", int(time.time() * 1000))
    print(json.dumps(event, ensure_ascii=False))

def truncate(s: str, n: int = 2000):
    s = s or ""
    return s if len(s) <= n else s[:n] + f"...(+{len(s)-n})"
