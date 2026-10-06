import asyncio
import contextvars
import os
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

# Correlates every log line of one resume analysis (set by main.py). Never holds user data.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def log(message: str) -> None:
    print(f"[job_search] [{request_id_var.get()}] {message}", flush=True)


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


# A request to a sleeping free-tier host can fail in ways that clear up on their own, so those
# are retried. Auth/URL/request errors are configuration problems; retrying would only repeat them.
MCP_MAX_ATTEMPTS = 3
MCP_RETRY_BACKOFF_SECONDS = (5, 15)
RETRYABLE_HTTP_STATUSES = {408, 425, 429, 500, 502, 503, 504}


class MCPCallError(RuntimeError):
    """An MCP call failed. `reason` is a short safe code the UI can show; `retryable` drives retries."""

    def __init__(self, message: str, reason: str, retryable: bool, status: int | None = None):
        super().__init__(message)
        self.reason = reason
        self.retryable = retryable
        self.status = status


def _leaf_exception(error: BaseException) -> BaseException:
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return error


def _classify(error: BaseException) -> MCPCallError:
    """Turns whatever the MCP/HTTP libraries raised into an MCPCallError (never contains secrets)."""
    leaf = _leaf_exception(error)
    if isinstance(leaf, MCPCallError):
        return leaf
    text = _root_cause(error)
    if isinstance(leaf, httpx.HTTPStatusError):
        status = leaf.response.status_code
        if status in (401, 403):
            return MCPCallError(text, "auth", False, status)
        if status in RETRYABLE_HTTP_STATUSES:
            return MCPCallError(text, "server_waking_or_unavailable", True, status)
        return MCPCallError(text, "bad_request", False, status)
    if isinstance(leaf, (httpx.TimeoutException, asyncio.TimeoutError, TimeoutError)):
        return MCPCallError(text, "timeout", True)
    if isinstance(leaf, (httpx.TransportError, OSError)):
        return MCPCallError(text, "unreachable", True)
    return MCPCallError(text, "error", False)


def _describe_endpoint() -> str:
    """Safe-to-log description of where MCP calls go (never the token)."""
    remote = _remote_server()
    return remote[0] if remote else "local STDIO subprocess"


def search_jobs_batch_via_mcp(queries: list[str], location: str = "", limit: int = 30) -> list[dict]:
    """
    Synchronous wrapper (the rest of HirePath is synchronous). Runs every query
    over a single MCP session. Returns one SearchResult dict per query, in order:
    {"source", "count", "jobs", "errors"}.

    Every call opens its own connection, so one request never depends on another.
    Transient failures (a sleeping host, timeouts, 502/503) are retried; auth and
    request errors are raised immediately as MCPCallError.
    """
    try:
        endpoint = _describe_endpoint()
    except RuntimeError as e:  # remote mode without a token
        raise MCPCallError(str(e), "not_configured", False) from None
    log(f"MCP request started: endpoint={endpoint}, queries={len(queries)}")

    for attempt in range(1, MCP_MAX_ATTEMPTS + 1):
        wake_remote_server()  # no-op unless MCP_SERVER_URL is set
        started = time.monotonic()
        try:
            results = asyncio.run(_call_search_jobs(queries, location, limit))
            log(f"MCP request completed: attempt={attempt}, {time.monotonic() - started:.1f}s")
            return results
        except BaseException as e:
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            # The MCP library wraps failures in a TaskGroup error whose message hides the cause.
            failure = _classify(e)
            log(f"MCP request failed: attempt={attempt}/{MCP_MAX_ATTEMPTS}, reason={failure.reason}, "
                f"status={failure.status}, error={failure}, retryable={failure.retryable}")
            if not failure.retryable or attempt == MCP_MAX_ATTEMPTS:
                raise failure from None
            time.sleep(MCP_RETRY_BACKOFF_SECONDS[min(attempt - 1, len(MCP_RETRY_BACKOFF_SECONDS) - 1)])


def _root_cause(error: BaseException) -> str:
    """Digs the real error out of nested exception groups, e.g. 'HTTPStatusError: 401 Unauthorized'."""
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    return f"{type(error).__name__}: {error}"[:200]


def search_jobs_via_mcp(query: str, location: str = "", limit: int = 30) -> dict:
    """Single-query convenience wrapper around the batch call."""
    return search_jobs_batch_via_mcp([query], location, limit)[0]


def check_mcp_connection(deep: bool = False) -> dict:
    """
    Safe, server-side MCP health check for the diagnostics endpoint. Proves the whole chain:
    /health, authentication, the MCP handshake and the tool list; with deep=True it also
    runs a real search_jobs call. Returns only booleans and short codes - never secrets.
    """
    report = {"mode": "remote" if os.environ.get("MCP_SERVER_URL", "").strip() else "stdio",
              "url_configured": bool(os.environ.get("MCP_SERVER_URL", "").strip()),
              "token_configured": bool(os.environ.get("MCP_AUTH_TOKEN", "").strip()),
              "health_ok": None, "auth_and_handshake_ok": False, "search_jobs_ok": None, "error": None}
    try:
        _describe_endpoint()
    except RuntimeError as e:
        report["error"] = {"reason": "not_configured", "detail": str(e)}
        return report
    if report["url_configured"]:
        report["health_ok"] = wake_remote_server(timeout=30)

    async def probe() -> bool:
        async with _open_streams() as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                if "search_jobs" not in tools:
                    raise MCPCallError("search_jobs tool is missing", "error", False)
                if deep:
                    result = await session.call_tool("search_jobs", {"query": "Python Developer", "limit": 1})
                    report["search_jobs_ok"] = not result.isError
        return True

    try:
        report["auth_and_handshake_ok"] = asyncio.run(probe())
    except BaseException as e:
        if isinstance(e, (KeyboardInterrupt, SystemExit)):
            raise
        failure = _classify(e)
        report["error"] = {"reason": failure.reason, "status": failure.status, "detail": str(failure)}
    return report
