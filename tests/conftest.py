import sys
import os

# Add the "backend" folder to Python's search path.
# This lets test files do things like: from app.tools.resume_parser import ...
backend_path = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, backend_path)

# Also add the project root so tests can import the mcp_server package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


import pytest


@pytest.fixture(autouse=True)
def _direct_job_search_by_default(monkeypatch):
    """Tests must not start a real MCP server; tests that want MCP mode set it themselves."""
    monkeypatch.setenv("JOB_SEARCH_MODE", "direct")
