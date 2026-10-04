import asyncio
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

# backend/app/services/mcp_job_client.py -> repo root (the folder that contains mcp_server/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


# The MCP SDK only forwards a small safe list of environment variables to the server
# subprocess, so the job-source credentials are passed explicitly. On Render they come
# from the service's environment variables; locally the server can also read its own .env.
SERVER_ENV_VARS = ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "JOOBLE_API_KEY")


def _server_env() -> dict[str, str]:
    return {name: os.environ[name] for name in SERVER_ENV_VARS if os.environ.get(name)}


def _server_params() -> StdioServerParameters:
    # The client launches the HirePath job MCP server as a subprocess (STDIO transport).
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
        env=_server_env(),
    )


# Remote mode: set MCP_SERVER_URL (the server's base address) and MCP_AUTH_TOKEN to use a
# deployed HirePath job MCP server over HTTP. Leave MCP_SERVER_URL unset to start the
# server locally as a subprocess instead.
# Generous because a free-tier host can need up to a minute to wake up after being idle.
HTTP_TIMEOUT_SECONDS = 90


def _remote_server() -> tuple[str, dict[str, str]] | None:
    """Returns (MCP endpoint URL, request headers) when remote mode is configured, else None."""
    base_url = os.environ.get("MCP_SERVER_URL", "").strip()
    if not base_url:
        return None
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MCP_SERVER_URL is set but MCP_AUTH_TOKEN is missing")
    url = base_url.rstrip("/")
    if not url.endswith("/mcp"):
        url += "/mcp"
    return url, {"Authorization": f"Bearer {token}"}


# A free-tier host puts an idle service to sleep. While it wakes (30-60 seconds) the gateway
# answers 502/503, so asking for jobs straight away would fail and fall back to the direct
# APIs. Polling /health first waits the wake-up out.
WAKE_TIMEOUT_SECONDS = 75
WAKE_POLL_SECONDS = 3


def wake_remote_server(timeout: float = WAKE_TIMEOUT_SECONDS) -> bool:
    """
    Waits until the remote MCP server answers /health. Returns True once it is up and
    False on timeout, or when remote mode is not configured. Never raises: if the server
    stays down, the normal search call fails and the caller falls back as usual.
    """
    base_url = os.environ.get("MCP_SERVER_URL", "").strip()
    if not base_url:
        return False
    health_url = base_url.rstrip("/").removesuffix("/mcp") + "/health"
    deadline = time.monotonic() + timeout
    while True:
        try:
            if requests.get(health_url, timeout=10).status_code == 200:
                return True
        except requests.RequestException:
            pass
        if time.monotonic() + WAKE_POLL_SECONDS >= deadline:
            return False
        time.sleep(WAKE_POLL_SECONDS)


def wake_remote_server_in_background() -> None:
    """Starts waking the server now, so the wake-up overlaps with other work (resume analysis)."""
    if os.environ.get("MCP_SERVER_URL", "").strip():
        threading.Thread(target=wake_remote_server, daemon=True).start()


@asynccontextmanager
async def _open_streams():
    """Connects to the MCP server (remote over HTTP, or a local subprocess) and yields (read, write)."""
    remote = _remote_server()
    if remote:
        url, headers = remote
        async with streamablehttp_client(url, headers=headers, timeout=HTTP_TIMEOUT_SECONDS) as (read, write, _):
            yield read, write
    else:
        async with stdio_client(_server_params()) as (read, write):
            yield read, write


async def _call_search_jobs(queries: list[str], location: str, limit: int) -> list[dict]:
    results = []
    async with _open_streams() as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # One connection and one session are reused for every query.
            for query in queries:
                result = await session.call_tool(
                    "search_jobs", {"query": query, "location": location, "limit": limit}
                )
                if result.isError:
                    raise RuntimeError(f"MCP search_jobs failed: {result.content[0].text}")
                results.append(result.structuredContent)
    return results


def search_jobs_batch_via_mcp(queries: list[str], location: str = "", limit: int = 30) -> list[dict]:
    """
    Synchronous wrapper (the rest of HirePath is synchronous). Runs every query
    over a single MCP session. Returns one SearchResult dict per query, in order:
    {"source", "count", "jobs", "errors"}.
    """
    wake_remote_server()  # no-op unless MCP_SERVER_URL is set
    try:
        return asyncio.run(_call_search_jobs(queries, location, limit))
    except BaseExceptionGroup as group:
        # The MCP library wraps failures in a TaskGroup error whose message hides the cause.
        raise RuntimeError(_root_cause(group)) from None


def _root_cause(error: BaseException) -> str:
    """Digs the real error out of nested exception groups, e.g. 'HTTPStatusError: 401 Unauthorized'."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return f"{type(error).__name__}: {error}"[:200]


def search_jobs_via_mcp(query: str, location: str = "", limit: int = 30) -> dict:
    """Single-query convenience wrapper around the batch call."""
    return search_jobs_batch_via_mcp([query], location, limit)[0]
