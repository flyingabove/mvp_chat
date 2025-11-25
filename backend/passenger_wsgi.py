import sys
import os

# Ensure this directory is on the Python path
sys.path.insert(0, os.path.dirname(__file__))

from app.main import app as application
