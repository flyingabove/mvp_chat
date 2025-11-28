import sys
import os
import threading
import uvicorn

# Setup path
sys.path.insert(0, "/home/storvrfx/beta_backend")

# Activate venv
activate_this = "/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py"
exec(open(activate_this).read(), {"__file__": activate_this})

# Import your FastAPI app from backend/app/main.py
from app.main import app

def run_server():
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8008,
        workers=1,
        loop="asyncio",
        http="h11",
    )

if "uvicorn_started" not in globals():
    uvicorn_started = True
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()

# Passenger WSGI fallback
def application(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"Uvicorn starting..."]
