# /home/storvrfx/beta_backend/passenger_wsgi.py

import sys
import os

# Ensure this directory is on the Python path
sys.path.insert(0, '/home/storvrfx/beta_backend')

# Activate virtualenv
activate_this = '/home/storvrfx/virtualenv/beta_backend/3.10/bin/activate_this.py'
if os.path.exists(activate_this):
    exec(open(activate_this).read(), {'__file__': activate_this})

# Import FastAPI application
from fastapi import FastAPI
from mangum import Mangum

app = FastAPI()

@app.get("/")
def root():
    return {"status": "ok"}

# Wrap FastAPI ASGI as WSGI for Passenger
handler = Mangum(app)

def application(environ, start_response):
    return handler(environ, start_response)
