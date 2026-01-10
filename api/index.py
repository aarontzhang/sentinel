import sys
import os

# Add project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import Flask app (Vercel auto-detects WSGI)
from app import app
