import os
from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.models.profile import CandidateProfile
from app.tools.adzuna_tool import search_adzuna_jobs
from app.tools.jooble_tool import search_jooble_jobs
from app.tools.arbeitnow_tool import search_arbeitnow_jobs
from app.services.mcp_job_client import MCPCallError, log, search_jobs_batch_via_mcp, search_jobs_via_mcp
from app.services.token_tracker import log_usage
from app.services.groq_client import build_structured_llm

load_dotenv()


class SearchQueries(BaseModel):
    queries: List[str] = Field(
        description="3 to 5 short, realistic job search terms (e.g. 'Python Developer', "
        "'Machine Learning Engineer') based on the candidate's skills and target roles"
    )


# Automatically falls back to GROQ_API_KEY_2 if the primary key's quota is exhausted.
structured_llm = build_structured_llm(SearchQueries, temperature=0)

QUERY_PROMPT = """You are a job search expert.
Based on the candidate's skills, technologies, and target roles, generate 3 to 5
short, realistic job search terms someone would type into a job board.

Rules:
- Keep each query short (2-4 words), like a real job title.
- Avoid duplicates.
- Base queries only on the candidate's actual skills/target roles. Do not invent unrelated roles.
"""


def generate_search_queries(candidate_profile: CandidateProfile) -> List[str]:
    """Uses the LLM to turn a candidate profile into a short list of job search terms."""
    profile_summary = f"""
Skills: {', '.join(candidate_profile.skills)}
Technologies: {', '.join(candidate_profile.technologies)}
Target Roles: {', '.join(candidate_profile.target_roles)}
Projects: {', '.join(p.name for p in candidate_profile.projects)}
Career Level: {candidate_profile.career_level}
"""
    messages = [
        ("system", QUERY_PROMPT),
        ("human", profile_summary),
    ]
    result = structured_llm.invoke(messages)
    log_usage("Job Search Agent (query generation)", result["raw"])

    if result["parsed"] is None:
        raise ValueError(f"Could not parse search queries: {result.get('parsing_error')}")

    return result["parsed"].queries


def _log_source_result(source: str, query: str, result: dict) -> None:
    """
    Prints one line per source per query so job-source failures (bad key,
    rate limit, unexpected response shape) are visible in server logs
    instead of silently vanishing into an empty list.
    """
    if result["success"]:
        print(f"[job_search] {source} '{query}': {len(result['jobs'])} job(s)", flush=True)
    else:
        print(f"[job_search] {source} '{query}' FAILED: {result.get('error', 'unknown error')}", flush=True)


def _jobs_from_mcp_result(query: str, result: dict) -> List[dict]:
    """
    The server already normalizes and de-duplicates, so jobs arrive in HirePath's
    common shape; we only add the two fields the Job Analysis Agent fills in later.
    """
    for source, error in result["errors"].items():
        print(f"[job_search] mcp {source} '{query}' FAILED: {error}", flush=True)
    print(f"[job_search] mcp '{query}': {result['count']} job(s)", flush=True)

    jobs = []
    for job in result["jobs"]:
        job["experience_required"] = "Unknown"
        job["skills_required"] = []
        jobs.append(job)
    return jobs


def search_via_mcp(query: str, location: str = "") -> List[dict]:
    """Asks the HirePath job MCP server for jobs for ONE query."""
    return _jobs_from_mcp_result(query, search_jobs_via_mcp(query, location=location))


def _mcp_mode_enabled() -> bool:
    return os.getenv("JOB_SEARCH_MODE", "mcp").lower() == "mcp"


def search_all_sources(query: str, location: str = "") -> List[dict]:
    """
    Gets jobs for one search query. Uses the MCP server by default; set
    JOB_SEARCH_MODE=direct to call the three job APIs directly.
    """
    if _mcp_mode_enabled():
        try:
            return search_via_mcp(query, location)
        except Exception as e:
            log(f"MCP fallback activated: {e}")

    return search_all_sources_direct(query, location)


def search_all_sources_direct(query: str, location: str = "") -> List[dict]:
    """
    Calls all three job APIs for one search query and combines the results.
    Each job dict is tagged with which source it came from.
    """
    all_jobs = []

    adzuna_result = search_adzuna_jobs(query, location=location)
    _log_source_result("adzuna", query, adzuna_result)
    if adzuna_result["success"]:
        for job in adzuna_result["jobs"]:
            job["_source"] = "adzuna"
            all_jobs.append(job)

    jooble_result = search_jooble_jobs(query, location=location)
    _log_source_result("jooble", query, jooble_result)
    if jooble_result["success"]:
        for job in jooble_result["jobs"]:
            job["_source"] = "jooble"
            all_jobs.append(job)

    arbeitnow_result = search_arbeitnow_jobs(query)
    _log_source_result("arbeitnow", query, arbeitnow_result)
    if arbeitnow_result["success"]:
        for job in arbeitnow_result["jobs"]:
            job["_source"] = "arbeitnow"
            all_jobs.append(job)

    return all_jobs


def search_jobs_for_candidate(candidate_profile: CandidateProfile, location: str = "") -> dict:
    """
    Full Job Search Agent flow:
    1. Generate smart search queries from the candidate's profile
    2. Search all 3 job sources for each query
    3. Return the combined raw job list + the queries used
    """
    queries = generate_search_queries(candidate_profile)

    all_jobs = []
    if queries and _mcp_mode_enabled():
        # One MCP session for all queries instead of one server process per query.
        try:
            results = search_jobs_batch_via_mcp(queries, location=location)
            for query, result in zip(queries, results):
                all_jobs.extend(_jobs_from_mcp_result(query, result))
            return {"search_queries": queries, "jobs": all_jobs, "search_via": "mcp"}
        except Exception as e:
            reason = e.reason if isinstance(e, MCPCallError) else "error"
            log(f"MCP fallback activated (reason={reason}): {e}")
            all_jobs = [job for query in queries for job in search_all_sources_direct(query, location)]
            return {"search_queries": queries, "jobs": all_jobs, "search_via": "direct", "search_via_reason": reason}

    for query in queries:
        all_jobs.extend(search_all_sources(query, location=location))

    return {"search_queries": queries, "jobs": all_jobs, "search_via": "mcp" if _mcp_mode_enabled() else "direct"}
