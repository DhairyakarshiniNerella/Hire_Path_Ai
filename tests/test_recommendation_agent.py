import pytest
from app.agents import recommendation_agent
from app.models.profile import CandidateProfile


class FakeAIMessage:
    def __init__(self, usage_metadata=None):
        self.usage_metadata = usage_metadata or {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}


class FakeExplanation:
    def __init__(self, why_it_matches="Great fit", experience_analysis="Compatible", skill_gap_summary="None"):
        self.why_it_matches = why_it_matches
        self.experience_analysis = experience_analysis
        self.skill_gap_summary = skill_gap_summary


class FakeStructuredLLM:
    """Stands in for the real ChatGroq structured_llm, which is a pydantic-based
    Runnable that rejects monkeypatching its 'invoke' attribute directly."""

    def __init__(self, invoke_fn):
        self.invoke = invoke_fn


@pytest.fixture
def spy_log_usage(monkeypatch):
    calls = []
    monkeypatch.setattr(recommendation_agent, "log_usage", lambda agent, raw: calls.append((agent, raw)))
    return calls


def make_profile(**overrides):
    defaults = dict(skills=["Python"], total_experience_years=2.0, career_level="Mid Level", target_roles=["Backend Developer"])
    defaults.update(overrides)
    return CandidateProfile(**defaults)


def make_job(**overrides):
    defaults = dict(
        title="Backend Developer", company="Acme", match_score=85,
        matched_skills=["Python"], missing_skills=[],
        experience_compatibility="Compatible", experience_gap=None, experience_required="2+ years",
    )
    defaults.update(overrides)
    return defaults


def test_generate_recommendation_success_sets_explanation_fields(monkeypatch, spy_log_usage):
    explanation = FakeExplanation(
        why_it_matches="Matches your Python skills",
        experience_analysis="You meet the requirement",
        skill_gap_summary="No gaps",
    )
    monkeypatch.setattr(
        recommendation_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": explanation, "parsing_error": None}),
    )

    result = recommendation_agent.generate_recommendation(make_profile(), make_job())

    assert result["why_it_matches"] == "Matches your Python skills"
    assert result["experience_analysis"] == "You meet the requirement"
    assert result["skill_gap_summary"] == "No gaps"
    assert spy_log_usage[0][0] == "Recommendation Agent"


def test_generate_recommendation_falls_back_on_llm_exception(monkeypatch, spy_log_usage):
    def boom(messages):
        raise RuntimeError("Groq unavailable")

    monkeypatch.setattr(recommendation_agent, "structured_llm", FakeStructuredLLM(boom))

    job = make_job(match_score=72, missing_skills=["Docker"])
    result = recommendation_agent.generate_recommendation(make_profile(), job)

    assert "72%" in result["why_it_matches"]
    assert "Compatible" in result["experience_analysis"]
    assert "Docker" in result["skill_gap_summary"]


def test_generate_recommendation_falls_back_when_parsing_fails(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        recommendation_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": None, "parsing_error": "bad output"}),
    )

    job = make_job(missing_skills=[])
    result = recommendation_agent.generate_recommendation(make_profile(), job)

    assert result["skill_gap_summary"] == "No major skill gaps found."


def test_generate_recommendation_fallback_never_crashes_on_missing_fields(monkeypatch, spy_log_usage):
    def boom(messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(recommendation_agent, "structured_llm", FakeStructuredLLM(boom))

    # A bare job dict missing most matcher-provided fields should still produce a fallback
    result = recommendation_agent.generate_recommendation(make_profile(), {"title": "X"})

    assert "0%" in result["why_it_matches"]
    assert "Unknown" in result["experience_analysis"]
    assert result["skill_gap_summary"] == "No major skill gaps found."


def test_generate_recommendations_caps_at_top_n(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        recommendation_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": FakeExplanation(), "parsing_error": None}),
    )

    ranked_jobs = [make_job(title=f"Job {i}") for i in range(15)]
    results = recommendation_agent.generate_recommendations(make_profile(), ranked_jobs)

    assert len(results) == recommendation_agent.TOP_N_RECOMMENDATIONS
    assert all("why_it_matches" in job for job in results)


def test_generate_recommendations_fewer_than_top_n_processes_all(monkeypatch, spy_log_usage):
    monkeypatch.setattr(
        recommendation_agent, "structured_llm",
        FakeStructuredLLM(lambda messages: {"raw": FakeAIMessage(), "parsed": FakeExplanation(), "parsing_error": None}),
    )

    ranked_jobs = [make_job(title="Only Job")]
    results = recommendation_agent.generate_recommendations(make_profile(), ranked_jobs)

    assert len(results) == 1


def test_generate_recommendations_empty_list(monkeypatch, spy_log_usage):
    assert recommendation_agent.generate_recommendations(make_profile(), []) == []
