from app.graph.state import WorkflowState


def supervisor_node(state: WorkflowState) -> dict:
    """
    Looks at what has already been completed in the shared state and decides
    which agent should run next. This is the coordination logic of the workflow.

    Important: we check "is None" rather than "not state.get(...)" for each
    stage. A stage that legitimately produced an empty list (e.g. zero jobs
    found) must still count as "done" - otherwise the Supervisor can't tell
    that apart from "hasn't run yet" and would loop on that stage forever.
    """

    # If a previous agent already reported a fatal error, stop the workflow
    if state.get("errors"):
        next_agent = "end"

    # Nothing done yet -> analyze the resume first
    elif state.get("candidate_profile") is None:
        next_agent = "resume_analyzer"

    # Job search hasn't run yet (None), even if it might end up finding 0 jobs
    elif state.get("jobs") is None:
        next_agent = "job_search"

    elif state.get("analyzed_jobs") is None:
        next_agent = "job_analysis"

    elif state.get("ranked_jobs") is None:
        next_agent = "matching"

    elif state.get("recommendations") is None:
        next_agent = "recommendation"

    # Everything is done
    else:
        next_agent = "end"

    return {"current_agent": next_agent}
