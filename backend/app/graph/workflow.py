from langgraph.graph import StateGraph, END
from app.graph.state import WorkflowState
from app.agents.supervisor_agent import supervisor_node
from app.agents.resume_agent import analyze_resume
from app.agents.job_search_agent import search_jobs_for_candidate
from app.agents.job_analysis_agent import analyze_jobs
from app.agents.matching_agent import rank_jobs_for_candidate
from app.agents.recommendation_agent import generate_recommendations
from app.services.job_normalizer import normalize_jobs, remove_duplicate_jobs, select_balanced_jobs
from app.services.error_messages import friendly_agent_error

# Analyzing every job with the LLM would mean hundreds of Groq calls per
# resume upload. We cap it to a manageable number of unique jobs.
MAX_JOBS_TO_ANALYZE = 15


def _node_error(agent_label: str, e: Exception) -> dict:
    """
    Logs the raw, technical exception to the server console (visible in
    Render's logs) so the real cause is always diagnosable, while the
    frontend only ever receives the short, friendly translation.
    """
    print(f"[error] {agent_label}: {e}", flush=True)
    return {"errors": [f"{agent_label} failed: {friendly_agent_error(e)}"]}


def resume_analyzer_node(state: WorkflowState) -> dict:
    """Graph node wrapper around the Resume Analyzer Agent."""
    try:
        profile = analyze_resume(state["resume_text"])
        return {"candidate_profile": profile}
    except Exception as e:
        return _node_error("Resume Analyzer Agent", e)


def job_search_node(state: WorkflowState) -> dict:
    """Graph node wrapper around the Job Search Agent."""
    try:
        result = search_jobs_for_candidate(state["candidate_profile"])
        return {"search_queries": result["search_queries"], "jobs": result["jobs"], "search_via": result["search_via"]}
    except Exception as e:
        return _node_error("Job Search Agent", e)


def job_analysis_node(state: WorkflowState) -> dict:
    """
    Graph node wrapper around the Job Analysis Agent.
    Normalizes and deduplicates the raw jobs first, then analyzes
    a capped number of unique jobs with the LLM.
    """
    try:
        normalized = normalize_jobs(state["jobs"])
        unique_jobs = remove_duplicate_jobs(normalized)
        jobs_to_analyze = select_balanced_jobs(unique_jobs, MAX_JOBS_TO_ANALYZE)
        analyzed = analyze_jobs(jobs_to_analyze)

        # analyze_job swallows per-job failures so one bad posting can't sink the run. But if
        # EVERY job failed (typically the AI service's rate limit), carrying on would score
        # empty jobs and end in a misleading "no matching jobs". Report the real cause instead.
        failures = [job["analysis_error"] for job in analyzed if job.get("analysis_error")]
        if analyzed and len(failures) == len(analyzed):
            raise RuntimeError(failures[0])

        return {"analyzed_jobs": analyzed}
    except Exception as e:
        return _node_error("Job Analysis Agent", e)


def matching_node(state: WorkflowState) -> dict:
    """Graph node wrapper around the Matching Agent."""
    try:
        ranked = rank_jobs_for_candidate(state["candidate_profile"], state["analyzed_jobs"])
        return {"ranked_jobs": ranked}
    except Exception as e:
        return _node_error("Matching Agent", e)


def recommendation_node(state: WorkflowState) -> dict:
    """Graph node wrapper around the Recommendation Agent."""
    try:
        recommendations = generate_recommendations(state["candidate_profile"], state["ranked_jobs"])
        return {"recommendations": recommendations}
    except Exception as e:
        return _node_error("Recommendation Agent", e)


def route_from_supervisor(state: WorkflowState) -> str:
    """
    Reads the 'current_agent' the Supervisor just decided and tells LangGraph
    which node to run next. Every agent is now built into the graph.
    """
    next_agent = state.get("current_agent", "end")
    return next_agent


# --- Build the graph ---
builder = StateGraph(WorkflowState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("resume_analyzer", resume_analyzer_node)
builder.add_node("job_search", job_search_node)
builder.add_node("job_analysis", job_analysis_node)
builder.add_node("matching", matching_node)
builder.add_node("recommendation", recommendation_node)

builder.set_entry_point("supervisor")

builder.add_conditional_edges(
    "supervisor",
    route_from_supervisor,
    {
        "resume_analyzer": "resume_analyzer",
        "job_search": "job_search",
        "job_analysis": "job_analysis",
        "matching": "matching",
        "recommendation": "recommendation",
        "end": END,
    },
)

builder.add_edge("resume_analyzer", "supervisor")
builder.add_edge("job_search", "supervisor")
builder.add_edge("job_analysis", "supervisor")
builder.add_edge("matching", "supervisor")
builder.add_edge("recommendation", "supervisor")

workflow = builder.compile()
