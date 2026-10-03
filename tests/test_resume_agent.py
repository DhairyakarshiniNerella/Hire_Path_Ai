import pytest
from app.agents import resume_agent
from app.models.profile import CandidateProfile


class FakeAIMessage:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


class FakeStructuredLLM:
    """Stands in for the real ChatGroq structured_llm, which is a pydantic-based
    Runnable that rejects monkeypatching its 'invoke' attribute directly."""

    def __init__(self, invoke_fn):
        self.invoke = invoke_fn


@pytest.fixture
def spy_log_usage(monkeypatch):
    calls = []
    monkeypatch.setattr(resume_agent, "log_usage", lambda agent, raw: calls.append((agent, raw)))
    return calls


def test_analyze_resume_returns_parsed_profile(monkeypatch, spy_log_usage):
    fake_profile = CandidateProfile(name="Jane Doe", skills=["Python"])
    fake_raw = FakeAIMessage()
    monkeypatch.setattr(
        resume_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": fake_raw, "parsed": fake_profile, "parsing_error": None}),
    )

    result = resume_agent.analyze_resume("Jane Doe\nSkills: Python")

    assert result is fake_profile
    assert spy_log_usage == [("Resume Analyzer Agent", fake_raw)]


def test_analyze_resume_sends_resume_text_in_messages(monkeypatch, spy_log_usage):
    captured = {}

    def fake_invoke(messages):
        captured["messages"] = messages
        return {"raw": FakeAIMessage(), "parsed": CandidateProfile(), "parsing_error": None}

    monkeypatch.setattr(resume_agent, "structured_llm", FakeStructuredLLM(fake_invoke))

    resume_agent.analyze_resume("My resume content here")

    system_role, system_text = captured["messages"][0]
    human_role, human_text = captured["messages"][1]
    assert system_role == "system"
    assert human_role == "human"
    assert "My resume content here" in human_text


def test_analyze_resume_raises_when_parsing_fails(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        resume_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": None, "parsing_error": "malformed output"}),
    )

    with pytest.raises(ValueError, match="malformed output"):
        resume_agent.analyze_resume("some resume text")

    # Every attempt's tokens are logged even though parsing failed -
    # each LLM call itself succeeded and cost tokens.
    assert len(spy_log_usage) == resume_agent.PARSE_ATTEMPTS


def test_analyze_resume_propagates_llm_exceptions(monkeypatch, spy_log_usage):
    def boom(messages):
        raise RuntimeError("Groq API unavailable")

    monkeypatch.setattr(resume_agent, "structured_llm", FakeStructuredLLM(boom))

    with pytest.raises(RuntimeError, match="Groq API unavailable"):
        resume_agent.analyze_resume("some resume text")

    assert spy_log_usage == []


# ---------- retry + server-side experience recomputation ----------

from app.models.profile import EmploymentPeriod

INTERNSHIP_RESUME = """Experience
Programmer/Analyst - II
NetApp, Bangalore June 2024 - Present
• Built things

Information Technology Internship
RPA Developer, NetApp, Bangalore Aug 2023 - June 2024
• Built bots
"""


def _llm_returning(profile):
    return FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": profile, "parsing_error": None})


def test_analyze_resume_retries_after_unparsable_output(monkeypatch, spy_log_usage):
    results = iter([
        {"raw": FakeAIMessage(), "parsed": None, "parsing_error": "bad"},
        {"raw": FakeAIMessage(), "parsed": CandidateProfile(name="Jane"), "parsing_error": None},
    ])
    monkeypatch.setattr(resume_agent, "structured_llm", FakeStructuredLLM(lambda m: next(results)))
    assert resume_agent.analyze_resume("text").name == "Jane"
    assert len(spy_log_usage) == 2


def test_internship_listed_by_model_is_dropped_and_total_recomputed(monkeypatch, spy_log_usage):
    profile = CandidateProfile(
        total_experience_years=3.0,  # model wrongly included the internship
        full_time_periods=[
            EmploymentPeriod(role="Programmer/Analyst - II", start="2024-06", end=""),
            EmploymentPeriod(role="RPA Developer", start="2023-08", end="2024-06"),
        ],
    )
    monkeypatch.setattr(resume_agent, "structured_llm", _llm_returning(profile))
    result = resume_agent.analyze_resume(INTERNSHIP_RESUME)
    assert [p.role for p in result.full_time_periods] == ["Programmer/Analyst - II"]
    assert result.total_experience_years < 3
    assert result.career_level in ("Entry Level", "Mid Level")


def test_only_internships_means_zero_experience_and_fresher(monkeypatch, spy_log_usage):
    profile = CandidateProfile(
        total_experience_years=1.0,
        full_time_periods=[EmploymentPeriod(role="Software Intern", start="2025-01", end="2025-06")],
    )
    monkeypatch.setattr(resume_agent, "structured_llm", _llm_returning(profile))
    result = resume_agent.analyze_resume("Software Intern Jan 2025 - Jun 2025")
    assert result.full_time_periods == []
    assert result.total_experience_years == 0
    assert result.career_level == "Fresher"


def test_no_periods_listed_keeps_the_models_own_total(monkeypatch, spy_log_usage):
    profile = CandidateProfile(total_experience_years=4.0, career_level="Mid Level")
    monkeypatch.setattr(resume_agent, "structured_llm", _llm_returning(profile))
    result = resume_agent.analyze_resume("resume without parsable dates")
    assert result.total_experience_years == 4.0
    assert result.career_level == "Mid Level"
