import sys
import os

# Ensure this directory (prod_backend / beta_backend) is on sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app.main import app as application
