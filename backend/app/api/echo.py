from fastapi import APIRouter, Request

router = APIRouter()

@router.post("/echo")
async def echo(request: Request):
    raw = await request.body()
    try:
        json_data = await request.json()
    except:
        json_data = None

    return {
        "ok": True,
        "method": request.method,
        "raw": raw.decode(),
        "json": json_data
    }
