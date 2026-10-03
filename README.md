# HirePath AI MCP

A Model Context Protocol (MCP) server that exposes job search as standard tools, together with **HirePath AI**, the multi-agent job-matching application that consumes it.

HirePath AI reads a candidate's resume, searches for jobs, analyzes them, and ranks them against the candidate's profile. This repository moves the job-search integrations (Adzuna, Jooble, Arbeitnow) out of the application and behind an MCP server. The application talks to one standard interface and receives normalized job data. It no longer needs to know how each source works.

## Contents

- [Why MCP](#why-mcp)
- [Architecture](#architecture)
- [MCP tools](#mcp-tools)
- [Job sources](#job-sources)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [Integration with HirePath AI](#integration-with-hirepath-ai)
- [The HirePath AI application](#the-hirepath-ai-application)
- [Project structure](#project-structure)
- [Design notes](#design-notes)
- [Known limitations](#known-limitations)
- [License](#license)

## Why MCP

Each job source has its own authentication, request format and response schema. Before MCP, HirePath AI called these APIs directly, so source-specific code lived inside the application.

With MCP:

- The job-search capability is **modular**: it can change or grow without touching the application.
- It is **reusable**: any MCP-compatible client can call the same tools.
- The application works with **one common job shape** instead of three.

MCP does not replace the REST APIs. The server still calls Adzuna, Jooble and Arbeitnow over HTTP. MCP is the standard, AI-facing interface placed in front of them.

## Architecture

```text
Resume -> Resume Parser -> Candidate Profile
                                 |
                          Job Search Agent        (generates queries with an LLM)
                                 |
                            MCP client            backend/app/services/mcp_job_client.py
                                 |  MCP over STDIO
                          Job MCP server          mcp_server/server.py
                                 |
                  search_jobs / search_jobs_by_source
                                 |
              Adzuna service | Jooble service | Arbeitnow service
                                 |
                    normalize -> interleave -> de-duplicate
                                 |
                          normalized jobs
                                 |
              HirePath AI: Job Analysis -> Matching -> Recommendations
```

**Responsibilities**

| MCP server | HirePath AI |
|---|---|
| Source API calls, authentication, timeouts, rate-limit handling | Resume parsing |
| Normalizing each source to one `Job` shape | LLM generation of search queries |
| Removing duplicates and mixing sources fairly | Job analysis, matching, recommendations |
| Input validation and per-source error reporting | Deciding when and what to search |

The server does not know what the candidate wants. The agent decides that and calls the tools.

**Request flow**

1. The Job Search Agent generates search queries from the candidate profile.
2. For each query, the MCP client starts the server (STDIO), initializes a session and calls `search_jobs`.
3. The server queries every source, normalizes the results, interleaves them, removes duplicates and applies the limit.
4. The result returns to HirePath AI as structured content, and the existing analysis and matching pipeline continues.

## MCP tools

| Tool | Arguments | Description |
|---|---|---|
| `search_jobs` | `query`, `location=""`, `limit=20` | Searches all sources and returns one merged, de-duplicated list. If a source fails, the other sources' jobs are still returned and the failure is listed in `errors`. |
| `search_jobs_by_source` | `source`, `query`, `location=""`, `limit=10` | Searches a single source: `adzuna`, `jooble` or `arbeitnow`. A failure is returned as a tool error. |
| `ping` | `message="hello"` | Connectivity test. |

Input is validated: an empty `query`, a `limit` outside 1-50, or an unknown `source` is rejected with a tool error.

### Example call

Request, sent by the client as JSON-RPC over STDIO:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "search_jobs",
    "arguments": { "query": "Python Developer", "location": "", "limit": 5 }
  }
}
```

Result, returned in `structuredContent`:

```json
{
  "source": "all",
  "count": 1,
  "jobs": [
    {
      "title": "Python Developer",
      "company": "Blumetra",
      "location": "Hyderabad, Telangana",
      "description": "...",
      "url": "https://...",
      "source": "Adzuna",
      "source_id": "123456",
      "employment_type": "full_time"
    }
  ],
  "errors": { "jooble": "Jooble rejected the API key" }
}
```

`errors` maps a source name to its error message and is empty when every source succeeded. The job shape is the same for every source.

### Error handling

| Situation | Behavior |
|---|---|
| Missing or invalid API key, timeout, rate limit, HTTP error | `search_jobs`: that source is skipped and reported in `errors`. `search_jobs_by_source`: returned as a tool error. |
| One source fails, others work | The working sources' jobs are returned. |
| No results | An empty `jobs` list with `count: 0`. |
| Empty query, bad `limit`, unknown source | Rejected before any API call. |
| API keys | Never included in error messages (the Jooble key is part of its URL). |

## Job sources

| Source | Credentials | Notes |
|---|---|---|
| Adzuna | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Country defaults to `in`; change with `ADZUNA_COUNTRY`. |
| Jooble | `JOOBLE_API_KEY` | The API has no limit parameter, so results are trimmed after the call. |
| Arbeitnow | none | The API has no search; the server filters locally by words in the title and tags. |

All three are free to use.

## Getting started

**Prerequisites:** Python 3.10 or newer. Free API keys for [Adzuna](https://developer.adzuna.com) and [Jooble](https://jooble.org/api/about). Arbeitnow needs no key. Running the full application also needs a [Groq](https://console.groq.com) key.

**MCP server only**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install "mcp<2" requests python-dotenv pydantic
```

**Full application** (the backend requirements include the MCP client and server dependencies)

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

`mcp` is pinned below 2.0 because MCP SDK 2.x renamed `FastMCP`, which the server uses.

## Configuration

Create `mcp_server/.env` from the template and add your keys:

```powershell
Copy-Item mcp_server\.env.example mcp_server\.env
```

```text
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
JOOBLE_API_KEY=
# Optional: ADZUNA_COUNTRY=in
```

`.env` files are gitignored. Never commit real keys.

The server reads its own `.env`. MCP clients pass only a small set of environment variables to a server subprocess, so keys exported in the client's shell do not reach it.

The full application additionally reads `backend/.env` (`GROQ_API_KEY`, optional `GROQ_API_KEY_2` as a quota fallback).

## Usage

The server uses the **STDIO** transport: a client starts it as a subprocess, so you normally do not run it by hand. To try it, use the included client from the repository root:

```powershell
python -m mcp_server.dev_client
```

It starts the server, lists the tools, calls `ping` and `search_jobs`, and prints the results. Always run the server as a module (`python -m mcp_server.server`) from the repository root. Running `python mcp_server/server.py` directly fails because its package imports cannot be resolved.

## Testing

```powershell
# from the repository root, with the backend virtual environment active
python -m pytest tests -q
```

The suite covers the MCP pieces (duplicate removal, the client path, fallback to direct APIs) along with the existing application tests. The live test client above exercises the real server and APIs.

## Integration with HirePath AI

Job search goes through the MCP server by default. `backend/app/agents/job_search_agent.py` reads the `JOB_SEARCH_MODE` environment variable:

| Value | Behavior |
|---|---|
| `mcp` (default) | Jobs come from the MCP server through the MCP client. If the server cannot be reached, the problem is logged and the direct APIs are used. |
| `direct` | The original direct API calls, with no MCP server involved. |

Start the backend:

```powershell
cd backend
.\venv\Scripts\python.exe -m app.main
```

To bypass MCP, set `$env:JOB_SEARCH_MODE = "direct"` before starting it.

The backend listens on `http://127.0.0.1:5000`. Run it from `backend\` as a module (`-m app.main`); running `main.py` from inside `app\` fails because the `app` package cannot be found.

Then open `frontend/index.html` in a browser. Query generation, analysis, matching and the frontend are unchanged. MCP jobs arrive already normalized, and the Job Search Agent adds the two fields the Job Analysis Agent fills in later.

## The HirePath AI application

HirePath AI is a multi-agent job recommendation system coordinated by LangGraph. A Supervisor agent inspects a shared workflow state and routes work to specialized agents:

1. **Resume Analyzer** turns resume text (PDF or DOCX) into a structured candidate profile using an LLM, without inventing missing data.
2. **Job Search** generates search queries from the profile and retrieves jobs, directly or through MCP.
3. **Job Analysis** extracts each job's requirements from its description.
4. **Matching** computes a weighted score (skills 35%, experience 25%, role 20%, projects 10%, education 10%) with deterministic Python and semantic embeddings. The LLM does not produce this number.
5. **Recommendation** explains each ranked match in plain language without changing the scores.

| Layer | Technology |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Flask |
| Orchestration | LangGraph, LangChain |
| LLM | Groq (free tier) |
| Embeddings | `all-MiniLM-L6-v2` through `fastembed` (ONNX, local) |
| Resume parsing | `pypdf`, `python-docx` |
| Validation | Pydantic |
| Job tools | MCP server (Adzuna, Jooble, Arbeitnow) |

## Project structure

```text
.
├── mcp_server/                  # MCP server
│   ├── server.py                # tool definitions
│   ├── models.py                # Job, SearchResult
│   ├── dedupe.py                # duplicate removal
│   ├── config.py                # reads mcp_server/.env
│   ├── dev_client.py            # terminal test client
│   ├── .env.example
│   └── services/
│       ├── adzuna.py
│       ├── jooble.py
│       └── arbeitnow.py
├── backend/                     # HirePath AI (Flask + LangGraph)
│   └── app/
│       ├── agents/              # supervisor and specialized agents
│       ├── graph/               # workflow state and graph
│       ├── services/            # normalizer, matcher, embeddings, MCP client
│       ├── tools/               # resume parser, direct job API clients
│       └── models/              # CandidateProfile
├── frontend/
├── tests/
└── README.md
```

## Design notes

- **Separation of layers.** `server.py` holds only tool definitions. API calls live in `services/`. Output shapes live in `models.py`.
- **Typed output.** Tools return Pydantic models, so clients receive a declared output schema and `structuredContent`.
- **Partial results.** One failing source does not fail a multi-source search.
- **Parallel sources.** `search_jobs` queries all sources at once in a thread pool and collects results in a fixed order, so a search takes about as long as the slowest source and the merged order stays predictable.
- **No source bias.** Results alternate between sources before the limit is applied, so one source cannot fill the list.
- **Incremental adoption.** The direct-API path remains as an opt-out (`JOB_SEARCH_MODE=direct`) and as an automatic fallback, so using MCP is reversible.
- **Scope.** Resume parsing and matching stay in the application. The server is an integration layer and does not make decisions.

## Known limitations

- The server process is started once per candidate search (one session for all queries), not kept running between searches.
- Only the STDIO transport is supported. There is no Streamable HTTP deployment yet.
- There is no `get_job_details` tool, because none of the three sources provides a detail endpoint in the current code.
- Arbeitnow matching is word-based, so "Python Developer" also returns non-Python "Developer" roles.
- Groq's free tier limits tokens per minute and per day. The application reports this as a friendly error.
- Job analysis is capped at 15 unique jobs per search.

## License

Built for educational and portfolio purposes.
