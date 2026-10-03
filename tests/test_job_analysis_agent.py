import pytest
from app.agents import job_analysis_agent


class FakeAIMessage:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


class FakeJobRequirements:
    def __init__(self, required_skills=None, preferred_skills=None, education_requirement="Unknown",
                 role="Unknown", technologies=None, responsibilities=None):
        self.required_skills = required_skills or []
        self.preferred_skills = preferred_skills or []
        self.education_requirement = education_requirement
        self.role = role
        self.technologies = technologies or []
        self.responsibilities = responsibilities or []


class FakeStructuredLLM:
    """Stands in for the real ChatGroq structured_llm, which is a pydantic-based
    Runnable that rejects monkeypatching its 'invoke' attribute directly."""

    def __init__(self, invoke_fn):
        self.invoke = invoke_fn


@pytest.fixture
def spy_log_usage(monkeypatch):
    calls = []
    monkeypatch.setattr(job_analysis_agent, "log_usage", lambda agent, raw: calls.append((agent, raw)))
    return calls


def test_analyze_job_merges_requirements_into_job_dict(monkeypatch, spy_log_usage):
    requirements = FakeJobRequirements(
        required_skills=["Python", "SQL"],
        preferred_skills=["Docker"],
        education_requirement="Bachelor's in CS",
        role="Backend Developer",
        technologies=["AWS"],
        responsibilities=["Build APIs"],
    )
    monkeypatch.setattr(
        job_analysis_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": requirements, "parsing_error": None}),
    )

    job = {"title": "Backend Dev", "description": "Requires Python and SQL"}
    result = job_analysis_agent.analyze_job(job)

    assert result["required_skills"] == ["Python", "SQL"]
    assert result["preferred_skills"] == ["Docker"]
    assert result["skills_required"] == ["Python", "SQL", "Docker"]
    assert result["education_requirement"] == "Bachelor's in CS"
    assert result["role"] == "Backend Developer"
    assert result["technologies"] == ["AWS"]
    assert result["responsibilities"] == ["Build APIs"]
    assert "analysis_error" not in result
    assert spy_log_usage[0][0] == "Job Analysis Agent"


def test_analyze_job_truncates_long_description(monkeypatch, spy_log_usage):
    captured = {}

    def fake_invoke(messages):
        captured["human_text"] = messages[1][1]
        return {"raw": FakeAIMessage(), "parsed": FakeJobRequirements(), "parsing_error": None}

    monkeypatch.setattr(job_analysis_agent, "structured_llm", FakeStructuredLLM(fake_invoke))

    long_description = "x" * 5000
    job_analysis_agent.analyze_job({"title": "T", "description": long_description})

    # description is capped at 3000 chars in the prompt
    assert captured["human_text"].count("x") == 3000


def test_analyze_job_returns_job_with_error_note_when_parsing_fails(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        job_analysis_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": None, "parsing_error": "malformed"}),
    )

    job = {"title": "Backend Dev", "description": "..."}
    result = job_analysis_agent.analyze_job(job)

    assert "analysis_error" in result
    assert "Job Analysis Agent failed" in result["analysis_error"]
    assert "required_skills" not in result


def test_analyze_job_never_crashes_on_llm_exception(monkeypatch, spy_log_usage):
    def boom(messages):
        raise RuntimeError("Groq timeout")

    monkeypatch.setattr(job_analysis_agent, "structured_llm", FakeStructuredLLM(boom))

    job = {"title": "Backend Dev", "description": "..."}
    result = job_analysis_agent.analyze_job(job)

    assert result["title"] == "Backend Dev"  # original job data preserved
    assert "Groq timeout" in result["analysis_error"]


def test_analyze_job_handles_missing_title_and_description(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        job_analysis_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": FakeJobRequirements(), "parsing_error": None}),
    )

    result = job_analysis_agent.analyze_job({})

    assert "analysis_error" not in result
    assert result["required_skills"] == []


def test_analyze_jobs_processes_every_job_independently(monkeypatch, spy_log_usage):
    def fake_invoke(messages):
        if "fails" in messages[1][1]:
            raise RuntimeError("boom")
        return {"raw": FakeAIMessage(), "parsed": FakeJobRequirements(required_skills=["Python"]), "parsing_error": None}

    monkeypatch.setattr(job_analysis_agent, "structured_llm", FakeStructuredLLM(fake_invoke))

    jobs = [
        {"title": "Good Job", "description": "works fine"},
        {"title": "Bad Job", "description": "this one fails"},
    ]
    results = job_analysis_agent.analyze_jobs(jobs)

    assert results[0]["required_skills"] == ["Python"]
    assert "analysis_error" in results[1]


def test_analyze_jobs_empty_list_returns_empty_list(monkeypatch, spy_log_usage):
    assert job_analysis_agent.analyze_jobs([]) == []
