from app.agents.supervisor_agent import supervisor_node


BASE_STATE = {
    "errors": [],
    "candidate_profile": None,
    "jobs": None,
    "analyzed_jobs": None,
    "ranked_jobs": None,
    "recommendations": None,
}


def state_with(**overrides):
    state = dict(BASE_STATE)
    state.update(overrides)
    return state


def test_routes_to_resume_analyzer_first():
    result = supervisor_node(state_with())
    assert result["current_agent"] == "resume_analyzer"


def test_routes_to_job_search_after_profile_ready():
    result = supervisor_node(state_with(candidate_profile=object()))
    assert result["current_agent"] == "job_search"


def test_routes_to_job_analysis_after_jobs_found():
    result = supervisor_node(state_with(candidate_profile=object(), jobs=[{"title": "x"}]))
    assert result["current_agent"] == "job_analysis"


def test_routes_to_job_analysis_even_when_zero_jobs_found():
    # An empty list means the stage ran and legitimately found nothing -
    # it must NOT be treated the same as "hasn't run yet" (None)
    result = supervisor_node(state_with(candidate_profile=object(), jobs=[]))
    assert result["current_agent"] == "job_analysis"


def test_routes_to_matching_after_analysis_done():
    result = supervisor_node(
        state_with(candidate_profile=object(), jobs=[], analyzed_jobs=[])
    )
    assert result["current_agent"] == "matching"


def test_routes_to_recommendation_after_ranking_done():
    result = supervisor_node(
        state_with(candidate_profile=object(), jobs=[], analyzed_jobs=[], ranked_jobs=[])
    )
    assert result["current_agent"] == "recommendation"


def test_routes_to_end_when_everything_done():
    result = supervisor_node(
        state_with(
            candidate_profile=object(), jobs=[], analyzed_jobs=[], ranked_jobs=[], recommendations=[]
        )
    )
    assert result["current_agent"] == "end"


def test_routes_to_end_when_errors_present_even_if_mid_pipeline():
    result = supervisor_node(state_with(errors=["Resume Analyzer Agent failed: boom"]))
    assert result["current_agent"] == "end"


def test_error_check_takes_priority_over_everything_else():
    result = supervisor_node(
        state_with(
            errors=["Job Search Agent failed"],
            candidate_profile=object(),
            jobs=None,
        )
    )
    assert result["current_agent"] == "end"
