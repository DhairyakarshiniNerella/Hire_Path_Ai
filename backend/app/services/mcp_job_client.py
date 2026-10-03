import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# backend/app/services/mcp_job_client.py -> repo root (the folder that contains mcp_server/)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


async def _call_search_jobs(query: str, location: str, limit: int) -> dict:
    # The client launches the HirePath job MCP server as a subprocess (STDIO transport).
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "search_jobs", {"query": query, "location": location, "limit": limit}
            )
            if result.isError:
                raise RuntimeError(f"MCP search_jobs failed: {result.content[0].text}")
            return result.structuredContent


def search_jobs_via_mcp(query: str, location: str = "", limit: int = 30) -> dict:
    """
    Synchronous wrapper (the rest of HirePath is synchronous).
    Returns the server's SearchResult as a dict: {"source", "count", "jobs", "errors"}.
    """
    return asyncio.run(_call_search_jobs(query, location, limit))
