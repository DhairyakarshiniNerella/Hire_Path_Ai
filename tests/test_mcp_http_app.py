import pytest
from starlette.testclient import TestClient

from mcp_server.http_app import build_app

TOKEN = "test-token-1234567890"
INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2025-03-26", "capabilities": {},
               "clientInfo": {"name": "t", "version": "0"}},
}
HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture
def client():
    with TestClient(build_app(TOKEN)) as c:
        yield c


def test_refuses_to_start_without_a_strong_token():
    for bad in ("", "short"):
        with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
            build_app(bad)


def test_health_is_open(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_mcp_endpoint_rejects_missing_token(client):
    r = client.post("/mcp", json=INIT, headers=HEADERS)
    assert r.status_code == 401


def test_mcp_endpoint_rejects_wrong_token(client):
    r = client.post("/mcp", json=INIT, headers={**HEADERS, "Authorization": "Bearer wrong-token-0000000"})
    assert r.status_code == 401


def test_mcp_endpoint_accepts_right_token_and_lists_tools(client):
    auth = {**HEADERS, "Authorization": f"Bearer {TOKEN}"}
    assert client.post("/mcp", json=INIT, headers=auth).status_code == 200

    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, headers=auth)
    names = {t["name"] for t in r.json()["result"]["tools"]}
    assert {"search_jobs", "search_jobs_by_source", "ping"} <= names
