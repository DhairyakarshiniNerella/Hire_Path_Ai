import asyncio
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

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
