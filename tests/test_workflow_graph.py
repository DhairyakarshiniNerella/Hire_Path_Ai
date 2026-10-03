from app.graph.workflow import (
    workflow,
    resume_analyzer_node,
    job_search_node,
    job_analysis_node,
    matching_node,
    recommendation_node,
    route_from_supervisor,
)
from app.graph import workflow as workflow_module


def test_workflow_compiles_without_error():
    # Regression guard for the "{don" syntax typo that previously broke
    # this module's import entirely.
    assert workflow is not None


def test_route_from_supervisor_reads_current_agent():
    assert route_from_supervisor({"current_agent": "matching"}) == "matching"


def test_route_from_supervisor_defaults_to_end_when_missing():
    assert route_from_supervisor({}) == "end"


def test_resume_analyzer_node_success(monkeypatch):
    fake_profile = object()
    monkeypatch.setattr(workflow_module, "analyze_resume", lambda text: fake_profile)
    result = resume_analyzer_node({"resume_text": "some text"})
    assert result == {"candidate_profile": fake_profile}


def test_resume_analyzer_node_catches_exceptions(monkeypatch):
    def boom(text):
        raise RuntimeError("LLM exploded")

    monkeypatch.setattr(workflow_module, "analyze_resume", boom)
    result = resume_analyzer_node({"resume_text": "some text"})
    assert "errors" in result
    assert "Resume Analyzer Agent failed" in result["errors"][0]


def test_job_search_node_success(monkeypatch):
    monkeypatch.setattr(
        workflow_module, "search_jobs_for_candidate",
        lambda profile: {"search_queries": ["Python Dev"], "jobs": [{"title": "x"}]},
    )
    result = job_search_node({"candidate_profile": object()})
    assert result == {"search_queries": ["Python Dev"], "jobs": [{"title": "x"}]}


def test_job_search_node_catches_exceptions(monkeypatch):
    def boom(profile):
        raise RuntimeError("API down")

    monkeypatch.setattr(workflow_module, "search_jobs_for_candidate", boom)
    result = job_search_node({"candidate_profile": object()})
    assert "Job Search Agent failed" in result["errors"][0]


def test_job_analysis_node_normalizes_dedupes_and_caps(monkeypatch):
    raw_jobs = [{"_source": "adzuna", "title": "A", "company": {}, "location": {}, "id": "1"}]
    monkeypatch.setattr(workflow_module, "normalize_jobs", lambda jobs: [{"title": "A"}])
    monkeypatch.setattr(workflow_module, "remove_duplicate_jobs", lambda jobs: jobs)
    monkeypatch.setattr(workflow_module, "analyze_jobs", lambda jobs: [{**j, "analyzed": True} for j in jobs])

    result = job_analysis_node({"jobs": raw_jobs})
    assert result["analyzed_jobs"] == [{"title": "A", "analyzed": True}]


def test_job_analysis_node_caps_at_max_jobs(monkeypatch):
    many_jobs = [{"title": f"Job {i}"} for i in range(20)]
    monkeypatch.setattr(workflow_module, "normalize_jobs", lambda jobs: jobs)
    monkeypatch.setattr(workflow_module, "remove_duplicate_jobs", lambda jobs: jobs)
    captured = {}

    def fake_analyze_jobs(jobs):
        captured["count"] = len(jobs)
        return jobs

    monkeypatch.setattr(workflow_module, "analyze_jobs", fake_analyze_jobs)
    job_analysis_node({"jobs": many_jobs})
    assert captured["count"] == workflow_module.MAX_JOBS_TO_ANALYZE


def test_job_analysis_node_catches_exceptions(monkeypatch):
    def boom(jobs):
        raise RuntimeError("normalize failed")

    monkeypatch.setattr(workflow_module, "normalize_jobs", boom)
    result = job_analysis_node({"jobs": []})
    assert "Job Analysis Agent failed" in result["errors"][0]


def test_matching_node_success(monkeypatch):
    monkeypatch.setattr(
        workflow_module, "rank_jobs_for_candidate",
        lambda profile, jobs: [{"title": "A", "match_score": 90}],
    )
    result = matching_node({"candidate_profile": object(), "analyzed_jobs": [{"title": "A"}]})
    assert result == {"ranked_jobs": [{"title": "A", "match_score": 90}]}


def test_matching_node_catches_exceptions(monkeypatch):
    def boom(profile, jobs):
        raise RuntimeError("scoring failed")

    monkeypatch.setattr(workflow_module, "rank_jobs_for_candidate", boom)
    result = matching_node({"candidate_profile": object(), "analyzed_jobs": []})
    assert "Matching Agent failed" in result["errors"][0]


def test_recommendation_node_success(monkeypatch):
    monkeypatch.setattr(
        workflow_module, "generate_recommendations",
        lambda profile, jobs: [{"title": "A", "why_it_matches": "great fit"}],
    )
    result = recommendation_node({"candidate_profile": object(), "ranked_jobs": [{"title": "A"}]})
    assert result == {"recommendations": [{"title": "A", "why_it_matches": "great fit"}]}


def test_recommendation_node_catches_exceptions(monkeypatch):
    def boom(profile, jobs):
        raise RuntimeError("explanation failed")

    monkeypatch.setattr(workflow_module, "generate_recommendations", boom)
    result = recommendation_node({"candidate_profile": object(), "ranked_jobs": []})
    assert "Recommendation Agent failed" in result["errors"][0]
