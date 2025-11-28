import sys
import os

# Ensure correct path
sys.path.insert(0, '/home/storvrfx/beta_backend')

# Activate venv
activate_this = '/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py'
exec(open(activate_this).read(), {'__file__': activate_this})

# Import FastAPI and ASGI->WSGI wrapper
from fastapi import FastAPI
from asgi_wsgi import ASGItoWSGI

app = FastAPI()

@app.get("/")
def root():
    return {"ok": True}

# Convert ASGI FastAPI app to WSGI for Passenger
application = ASGItoWSGI(app)
