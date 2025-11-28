import sys
import os
import threading
import uvicorn
import traceback

# Ensure backend is in Python path
sys.path.insert(0, "/home/storvrfx/beta_backend")

# Activate virtualenv
activate_this = "/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py"
exec(open(activate_this).read(), {"__file__": activate_this})

# Import your FastAPI app (REAL app)
try:
    from app.main import app
except Exception:
    with open("/home/storvrfx/beta_backend/stderr.log", "a") as f:
        f.write("\nIMPORT ERROR:\n")
        traceback.print_exc(file=f)
    raise

def run_server():
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8055,
        loop="asyncio",
        http="h11"
    )

if "uvicorn_started" not in globals():
    uvicorn_started = True
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()

def application(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"Uvicorn starting..."]
