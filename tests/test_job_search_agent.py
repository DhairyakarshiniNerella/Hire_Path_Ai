import pytest
from app.agents import job_search_agent
from app.models.profile import CandidateProfile


class FakeAIMessage:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


class FakeSearchQueries:
    def __init__(self, queries):
        self.queries = queries


class FakeStructuredLLM:
    """Stands in for the real ChatGroq structured_llm, which is a pydantic-based
    Runnable that rejects monkeypatching its 'invoke' attribute directly."""

    def __init__(self, invoke_fn):
        self.invoke = invoke_fn


@pytest.fixture
def spy_log_usage(monkeypatch):
    calls = []
    monkeypatch.setattr(job_search_agent, "log_usage", lambda agent, raw: calls.append((agent, raw)))
    return calls


# ---------- generate_search_queries ----------

def test_generate_search_queries_returns_parsed_list(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        job_search_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {
            "raw": FakeAIMessage(),
            "parsed": FakeSearchQueries(["Python Developer", "Backend Engineer"]),
            "parsing_error": None,
        }),
    )
    profile = CandidateProfile(skills=["Python"], technologies=["Docker"], target_roles=["Backend Developer"])

    result = job_search_agent.generate_search_queries(profile)

    assert result == ["Python Developer", "Backend Engineer"]
    assert spy_log_usage[0][0] == "Job Search Agent (query generation)"


def test_generate_search_queries_raises_when_parsing_fails(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        job_search_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": None, "parsing_error": "bad format"}),
    )
    profile = CandidateProfile()

    with pytest.raises(ValueError, match="bad format"):
        job_search_agent.generate_search_queries(profile)


def test_generate_search_queries_profile_summary_includes_fields(monkeypatch, spy_log_usage):
    captured = {}

    def fake_invoke(messages):
        captured["human_text"] = messages[1][1]
        return {"raw": FakeAIMessage(), "parsed": FakeSearchQueries(["X"]), "parsing_error": None}

    monkeypatch.setattr(job_search_agent, "structured_llm", FakeStructuredLLM(fake_invoke))
    profile = CandidateProfile(
        skills=["Python", "SQL"], technologies=["AWS"], target_roles=["Data Engineer"], career_level="Mid Level"
    )

    job_search_agent.generate_search_queries(profile)

    assert "Python, SQL" in captured["human_text"]
    assert "AWS" in captured["human_text"]
    assert "Data Engineer" in captured["human_text"]
    assert "Mid Level" in captured["human_text"]


# ---------- search_all_sources ----------

def test_search_all_sources_combines_and_tags_by_source(monkeypatch):
    monkeypatch.setattr(
        job_search_agent, "search_adzuna_jobs",
        lambda query, location="": {"success": True, "jobs": [{"title": "Adzuna Job"}]},
    )
    monkeypatch.setattr(
        job_search_agent, "search_jooble_jobs",
        lambda query, location="": {"success": True, "jobs": [{"title": "Jooble Job"}]},
    )
    monkeypatch.setattr(
        job_search_agent, "search_arbeitnow_jobs",
        lambda query: {"success": True, "jobs": [{"title": "Arbeitnow Job"}]},
    )

    result = job_search_agent.search_all_sources("Python Developer")

    sources = {job["title"]: job["_source"] for job in result}
    assert sources == {
        "Adzuna Job": "adzuna",
        "Jooble Job": "jooble",
        "Arbeitnow Job": "arbeitnow",
    }


def test_search_all_sources_skips_failed_source_without_crashing(monkeypatch):
    monkeypatch.setattr(
        job_search_agent, "search_adzuna_jobs",
        lambda query, location="": {"success": False, "error": "credentials missing"},
    )
    monkeypatch.setattr(
        job_search_agent, "search_jooble_jobs",
        lambda query, location="": {"success": True, "jobs": [{"title": "Jooble Job"}]},
    )
    monkeypatch.setattr(
        job_search_agent, "search_arbeitnow_jobs",
        lambda query: {"success": False, "error": "timeout"},
    )

    result = job_search_agent.search_all_sources("Python Developer")

    assert len(result) == 1
    assert result[0]["title"] == "Jooble Job"


def test_search_all_sources_all_fail_returns_empty_list(monkeypatch):
    monkeypatch.setattr(job_search_agent, "search_adzuna_jobs", lambda query, location="": {"success": False})
    monkeypatch.setattr(job_search_agent, "search_jooble_jobs", lambda query, location="": {"success": False})
    monkeypatch.setattr(job_search_agent, "search_arbeitnow_jobs", lambda query: {"success": False})

    assert job_search_agent.search_all_sources("Python Developer") == []


# ---------- search_jobs_for_candidate ----------

def test_search_jobs_for_candidate_searches_every_generated_query(monkeypatch):
    monkeypatch.setattr(job_search_agent, "generate_search_queries", lambda profile: ["Query A", "Query B"])

    call_log = []

    def fake_search_all_sources(query, location=""):
        call_log.append(query)
        return [{"title": f"Job for {query}"}]

    monkeypatch.setattr(job_search_agent, "search_all_sources", fake_search_all_sources)

    result = job_search_agent.search_jobs_for_candidate(CandidateProfile())

    assert call_log == ["Query A", "Query B"]
    assert result["search_queries"] == ["Query A", "Query B"]
    assert len(result["jobs"]) == 2


def test_search_jobs_for_candidate_passes_location_through(monkeypatch):
    monkeypatch.setattr(job_search_agent, "generate_search_queries", lambda profile: ["Query A"])
    captured = {}

    def fake_search_all_sources(query, location=""):
        captured["location"] = location
        return []

    monkeypatch.setattr(job_search_agent, "search_all_sources", fake_search_all_sources)

    job_search_agent.search_jobs_for_candidate(CandidateProfile(), location="Chennai")

    assert captured["location"] == "Chennai"


def test_search_jobs_for_candidate_no_queries_returns_no_jobs(monkeypatch):
    monkeypatch.setattr(job_search_agent, "generate_search_queries", lambda profile: [])
    monkeypatch.setattr(job_search_agent, "search_all_sources", lambda query, location="": [{"title": "x"}])

    result = job_search_agent.search_jobs_for_candidate(CandidateProfile())

    assert result == {"search_queries": [], "jobs": []}
