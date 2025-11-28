import sys
import os
import threading
import uvicorn

# Ensure backend directory is in python path
sys.path.insert(0, "/home/storvrfx/beta_backend")

# Activate virtualenv
activate_this = "/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py"
exec(open(activate_this).read(), {"__file__": activate_this})

# Import your FastAPI app
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

@app.get("/version")
def version():
    return {"version": "beta-4"}

# Start Uvicorn server inside Passenger only once
def run_server():
    uvicorn.run(
        "passenger_wsgi:app",
        host="127.0.0.1",
        port=8003,
        workers=1,
        loop="asyncio",
        http="h11"
    )

if "uvicorn_started" not in globals():
    uvicorn_started = True
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()

# Minimal WSGI fallback – prevents overriding API responses
def application(environ, start_response):
    start_response("503 Service Unavailable", [('Content-Type', 'text/plain')])
    return [b"Uvicorn starting..."]
