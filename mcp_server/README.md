# HirePath job MCP server

MCP server exposing job search (Adzuna, Jooble, Arbeitnow) as tools: `search_jobs`, `search_jobs_by_source`, `ping`.

Full documentation (architecture, tool reference, configuration, testing, integration) is in the [repository README](../README.md).

Quick start, from the repository root:

```powershell
Copy-Item mcp_server\.env.example mcp_server\.env   # then add your keys
python -m mcp_server.dev_client
```
