from concurrent.futures import ThreadPoolExecutor

from mcp.server.fastmcp import FastMCP

from mcp_server.dedupe import remove_duplicates
from mcp_server.models import Job, SearchResult
from mcp_server.services import adzuna, arbeitnow, jooble

mcp = FastMCP("hirepath-jobs")

# source name -> function(query, location, limit) -> list[Job]
SOURCES = {
    "adzuna": adzuna.search,
    "jooble": jooble.search,
    "arbeitnow": lambda query, location, limit: arbeitnow.search(query, location)[:limit],
}


def _validate(query: str, limit: int) -> None:
    if not query.strip():
        raise ValueError("query must not be empty")
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")


def _interleave(jobs_by_source: dict[str, list[Job]]) -> list[Job]:
    """Take one job from each source in turn so no single source dominates the list."""
    lists = [list(jobs) for jobs in jobs_by_source.values()]
    merged = []
    while any(lists):
        for jobs in lists:
            if jobs:
                merged.append(jobs.pop(0))
    return merged


@mcp.tool()
def ping(message: str = "hello") -> str:
    """Test tool: echoes the message back so we can check the server works."""
    return f"pong: {message}"


@mcp.tool()
def search_jobs_by_source(source: str, query: str, location: str = "", limit: int = 10) -> SearchResult:
    """
    Search ONE job source and return normalized jobs.
    source: adzuna, jooble or arbeitnow.
    query: job title or keywords, e.g. "Python Developer".
    location: optional location text, e.g. "Bangalore".
    limit: maximum number of jobs to return (1-50).
    """
    source = source.strip().lower()
    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Supported: {', '.join(SOURCES)}")
    _validate(query, limit)

    # If this single source fails there is nothing to return, so the error propagates.
    jobs = SOURCES[source](query.strip(), location.strip(), limit)
    return SearchResult(source=source, count=len(jobs), jobs=jobs)


@mcp.tool()
def search_jobs(query: str, location: str = "", limit: int = 20) -> SearchResult:
    """
    Search ALL job sources (Adzuna, Jooble, Arbeitnow) and return one merged list
    of normalized jobs, alternating between sources. If a source fails, the other
    sources' jobs are still returned and the failure is listed in `errors`.
    query: job title or keywords, e.g. "Python Developer".
    location: optional location text, e.g. "Bangalore".
    limit: maximum total number of jobs to return (1-50).
    """
    _validate(query, limit)

    jobs_by_source: dict[str, list[Job]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        # Start every source at once...
        futures = {
            name: pool.submit(search, query.strip(), location.strip(), limit)
            for name, search in SOURCES.items()
        }
        # ...then collect in a fixed order so the merged result order is stable.
        for name, future in futures.items():
            try:
                jobs_by_source[name] = future.result()
            except RuntimeError as e:  # one source failing must not fail the whole search
                errors[name] = str(e)

    jobs = remove_duplicates(_interleave(jobs_by_source))[:limit]
    return SearchResult(source="all", count=len(jobs), jobs=jobs, errors=errors)


if __name__ == "__main__":
    # STDIO transport: the client launches this script and talks to it
    # through stdin/stdout. No port is opened.
    mcp.run(transport="stdio")
