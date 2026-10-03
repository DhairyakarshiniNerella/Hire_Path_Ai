import sys
import os

# Add the "backend" folder to Python's search path.
# This lets test files do things like: from app.tools.resume_parser import ...
backend_path = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_path)
