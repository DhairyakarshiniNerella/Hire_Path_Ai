import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# backend/app/services/mcp_job_client.py -> repo root (the folder that contains mcp_server/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def _call_search_jobs(queries: list[str], location: str, limit: int) -> list[dict]:
    # The client launches the HirePath job MCP server as a subprocess (STDIO transport).
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )
    results = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            # One server process and one session are reused for every query.
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
    return asyncio.run(_call_search_jobs(queries, location, limit))


def search_jobs_via_mcp(query: str, location: str = "", limit: int = 30) -> dict:
    """Single-query convenience wrapper around the batch call."""
    return search_jobs_batch_via_mcp([query], location, limit)[0]
