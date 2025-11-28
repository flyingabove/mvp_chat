import sys
import os

sys.path.insert(0, "/home/storvrfx/beta_backend")

# Activate Passenger virtualenv
activate_this = "/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py"
exec(open(activate_this).read(), {"__file__": activate_this})

import threading
import uvicorn
from fastapi import FastAPI

# FastAPI app
app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

# Start uvicorn server INSIDE Passenger
def run_server():
    uvicorn.run(
        "passenger_wsgi:app",
        host="127.0.0.1",
        port=8003,
        workers=1,
        loop="asyncio",
        http="h11",
    )

# Start only once
if "uvicorn_started" not in globals():
    uvicorn_started = True
    thread = threading.Thread(target=run_server)
    thread.daemon = True
    thread.start()

# Dummy WSGI callable (Passenger only needs this)
def application(environ, start_response):
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"Uvicorn server running"]
