"""Tiny MCP client for testing the server from the terminal (no Node.js needed)."""
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    # 1. Describe how to start the server (the client launches it as a subprocess)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(PROJECT_ROOT),  # so Python can find the mcp_server package
    )

    # 2. Open the STDIO connection to the server
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            # 3. Handshake: client and server agree on the protocol
            await session.initialize()

            # 4. Tool discovery: ask the server what tools it has
            tools = await session.list_tools()
            print("TOOLS FOUND:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description}")
                print(f"    input schema: {tool.inputSchema}")

            # 5. Tool invocation: call the ping tool
            result = await session.call_tool("ping", {"message": "hello"})
            print("\nping result:", result.content[0].text)

            args = {"query": "Python Developer", "location": "", "limit": 9}
            print("\nCALL search_jobs", args)
            result = await session.call_tool("search_jobs", args)
            if result.isError:
                print("ERROR:", result.content[0].text)
            else:
                data = result.structuredContent
                print("count:", data["count"])
                for job in data["jobs"]:
                    print(f"  - [{job['source']}] {job['title']} | {job['company']} | {job['location']}")
                print("errors:", data["errors"])


if __name__ == "__main__":
    asyncio.run(main())
