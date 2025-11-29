from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/echo")
async def echo(request: Request):
    """
    Python equivalent of backend/api/echo.php

    Returns:
      {
        "method": "<HTTP method>",
        "raw": "<raw body as string>",
        "json": <parsed JSON or null>
      }
    """
    raw_bytes = await request.body()
    try:
        json_data = await request.json()
    except Exception:
        json_data = None

    return {
        "method": request.method,
        "raw": raw_bytes.decode("utf-8", errors="replace"),
        "json": json_data,
    }
