import pytest
from app.services import matcher
from app.models.profile import CandidateProfile, ProjectEntry


# ---------- match_skills ----------

def test_match_skills_exact_matches():
    result = matcher.match_skills(["Python", "SQL"], ["Python", "SQL"])
    assert set(result["matched_skills"]) == {"Python", "SQL"}
    assert result["missing_skills"] == []
    assert result["skill_match_score"] == 1.0


def test_match_skills_case_insensitive():
    result = matcher.match_skills(["python"], ["Python"])
    assert result["matched_skills"] == ["Python"]
    assert result["skill_match_score"] == 1.0


def test_match_skills_substring_match():
    # "React" candidate skill should satisfy "React.js" requirement and vice versa
    result = matcher.match_skills(["React"], ["React.js"])
    assert result["matched_skills"] == ["React.js"]


def test_match_skills_missing_skills_reported():
    result = matcher.match_skills(["Python"], ["Python", "Java"])
    assert result["missing_skills"] == ["Java"]
    assert result["skill_match_score"] == 0.5


def test_match_skills_no_required_falls_back_to_preferred():
    result = matcher.match_skills(["Python"], [], job_preferred_skills=["Python", "Docker"])
    assert result["skill_match_score"] == 0.5
    assert result["missing_skills"] == []  # missing is only computed from required


def test_match_skills_no_required_or_preferred_scores_zero():
    result = matcher.match_skills(["Python"], [])
    assert result["skill_match_score"] == 0.0
    assert result["matched_skills"] == []


def test_match_skills_candidate_has_no_skills():
    result = matcher.match_skills([], ["Python"])
    assert result["skill_match_score"] == 0.0
    assert result["missing_skills"] == ["Python"]


def test_match_skills_required_wins_key_collision_with_preferred():
    result = matcher.match_skills(["Python"], ["Python"], job_preferred_skills=["Python"])
    assert result["matched_skills"] == ["Python"]  # not duplicated


# ---------- check_experience_compatibility ----------

def test_experience_compatibility_unknown_when_no_requirement():
    result = matcher.check_experience_compatibility(3.0, None, None, "Unknown")
    assert result["experience_compatibility"] == "Unknown"
    assert result["experience_gap"] is None


def test_experience_compatibility_compatible_when_meets_minimum():
    result = matcher.check_experience_compatibility(3.0, 2.0, 5.0, "2-5 years")
    assert result["experience_compatibility"] == "Compatible"
    assert result["experience_gap"] is None


def test_experience_compatibility_compatible_when_exactly_minimum():
    result = matcher.check_experience_compatibility(2.0, 2.0, None, "2+ years")
    assert result["experience_compatibility"] == "Compatible"


def test_experience_compatibility_low_when_below_minimum():
    result = matcher.check_experience_compatibility(1.0, 3.0, 5.0, "3-5 years")
    assert result["experience_compatibility"] == "Low"
    assert "3-5 years" in result["experience_gap"]
    assert "1" in result["experience_gap"]


def test_experience_compatibility_overqualified_when_far_past_max():
    result = matcher.check_experience_compatibility(10.0, 1.0, 3.0, "1-3 years")
    assert result["experience_compatibility"] == "Overqualified"
    assert result["experience_gap"] is not None


def test_experience_compatibility_not_overqualified_within_3_year_buffer():
    # candidate_years (5) > max (3) but within the +3 buffer -> still just Compatible
    result = matcher.check_experience_compatibility(5.0, 1.0, 3.0, "1-3 years")
    assert result["experience_compatibility"] == "Compatible"


def test_experience_compatibility_boundary_exactly_at_buffer_edge():
    # max=3, candidate=6 -> candidate_years > max + 3 is False (6 > 6 is False) -> Compatible
    result = matcher.check_experience_compatibility(6.0, 1.0, 3.0, "1-3 years")
    assert result["experience_compatibility"] == "Compatible"


def test_experience_compatibility_boundary_just_past_buffer_edge():
    result = matcher.check_experience_compatibility(6.1, 1.0, 3.0, "1-3 years")
    assert result["experience_compatibility"] == "Overqualified"


# ---------- calculate_match_score (mocking the embedding call) ----------

@pytest.fixture
def mock_similarity(monkeypatch):
    """Avoid loading the real HuggingFace embedding model in unit tests."""
    calls = {}

    def fake_similarity(text_a, text_b):
        calls[(text_a, text_b)] = calls.get((text_a, text_b), 0) + 1
        return 0.7  # ceiling value -> rescales to 1.0

    monkeypatch.setattr(matcher, "compute_semantic_similarity", fake_similarity)
    return calls


def make_profile(**overrides):
    defaults = dict(
        skills=["Python", "SQL"],
        target_roles=["Backend Developer"],
        job_titles=[],
        projects=[ProjectEntry(name="Tool", description="A tool")],
        education=["B.Tech Computer Science"],
        total_experience_years=3.0,
    )
    defaults.update(overrides)
    return CandidateProfile(**defaults)


def make_job(**overrides):
    defaults = dict(
        title="Backend Developer",
        role="Backend Developer",
        description="Requires 2-4 years of experience with Python and SQL",
        required_skills=["Python", "SQL"],
        preferred_skills=[],
        education_requirement="Bachelor's degree",
    )
    defaults.update(overrides)
    return defaults


def test_calculate_match_score_full_match_scores_high(mock_similarity):
    profile = make_profile()
    job = make_job()
    result = matcher.calculate_match_score(profile, job)
    assert result["match_score"] > 80
    assert result["matched_skills"]
    assert result["missing_skills"] == []
    assert result["experience_compatibility"] == "Compatible"


def test_calculate_match_score_no_projects_uses_neutral_score(mock_similarity):
    profile = make_profile(projects=[])
    job = make_job()
    result = matcher.calculate_match_score(profile, job)
    assert result["project_match_score"] == 0.5


def test_calculate_match_score_missing_skills_lowers_score(mock_similarity):
    profile = make_profile(skills=["Java"])
    job = make_job(required_skills=["Python", "SQL", "Docker"])
    result = matcher.calculate_match_score(profile, job)
    assert result["skill_match_score"] == 0.0
    assert set(result["missing_skills"]) == {"Python", "SQL", "Docker"}


def test_calculate_match_score_low_experience_reduces_score(mock_similarity):
    profile = make_profile(total_experience_years=0.0)
    job = make_job(description="Requires 5+ years of experience")
    result = matcher.calculate_match_score(profile, job)
    assert result["experience_compatibility"] == "Low"


def test_calculate_match_score_uses_skills_required_alias_key(mock_similarity):
    # matcher falls back to job["skills_required"] when "required_skills" is absent
    profile = make_profile()
    job = make_job()
    del job["required_skills"]
    job["skills_required"] = ["Python", "SQL"]
    result = matcher.calculate_match_score(profile, job)
    assert result["skill_match_score"] == 1.0


def test_calculate_match_score_unknown_education_requirement_not_penalized(mock_similarity):
    profile = make_profile(education=[])
    job = make_job(education_requirement="Unknown")
    result = matcher.calculate_match_score(profile, job)
    assert result["education_match_score"] == 0.7


def test_rescale_similarity_floor_and_ceiling():
    assert matcher._rescale_similarity(0.05) == 0.0
    assert matcher._rescale_similarity(0.1) == 0.0
    assert matcher._rescale_similarity(0.7) == 1.0
    assert matcher._rescale_similarity(0.9) == 1.0


def test_rescale_similarity_midpoint():
    # halfway between floor (0.1) and ceiling (0.7) -> 0.5
    assert matcher._rescale_similarity(0.4) == pytest.approx(0.5)
