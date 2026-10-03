import pytest
from pydantic import ValidationError
from app.models.profile import CandidateProfile, ProjectEntry


def test_candidate_profile_defaults():
    profile = CandidateProfile()
    assert profile.name is None
    assert profile.email is None
    assert profile.education == []
    assert profile.skills == []
    assert profile.projects == []
    assert profile.internships == []
    assert profile.experience == []
    assert profile.total_experience_years == 0.0
    assert profile.job_titles == []
    assert profile.companies == []
    assert profile.technologies == []
    assert profile.career_level == "Unknown"
    assert profile.target_roles == []


def test_candidate_profile_full_construction():
    profile = CandidateProfile(
        name="Jane Doe",
        email="jane@example.com",
        education=["B.Tech CS, 2022"],
        skills=["Python", "SQL"],
        projects=[ProjectEntry(name="HirePath AI", description="Job matching system")],
        internships=["Intern at Acme"],
        experience=["Backend Dev at Beta, 2 years"],
        total_experience_years=2.5,
        job_titles=["Backend Developer"],
        companies=["Beta"],
        technologies=["Docker", "AWS"],
        career_level="Mid Level",
        target_roles=["Backend Engineer", "Python Developer"],
    )
    assert profile.name == "Jane Doe"
    assert profile.projects[0].name == "HirePath AI"
    assert profile.total_experience_years == 2.5


def test_candidate_profile_two_instances_do_not_share_mutable_defaults():
    # Regression guard: default_factory=list must give each instance its own list
    profile_a = CandidateProfile()
    profile_b = CandidateProfile()
    profile_a.skills.append("Python")
    assert profile_b.skills == []


def test_project_entry_default_description_is_empty_string():
    project = ProjectEntry(name="Resume Parser Tool")
    assert project.description == ""


def test_project_entry_requires_name():
    with pytest.raises(ValidationError):
        ProjectEntry()


def test_candidate_profile_model_dump_serializes_nested_projects():
    profile = CandidateProfile(
        skills=["Python"],
        projects=[ProjectEntry(name="Tool", description="Does things")],
    )
    dumped = profile.model_dump()
    assert dumped["projects"] == [{"name": "Tool", "description": "Does things"}]
    assert dumped["skills"] == ["Python"]


def test_candidate_profile_rejects_wrong_type_for_total_experience_years():
    with pytest.raises(ValidationError):
        CandidateProfile(total_experience_years="not a number")


def test_candidate_profile_coerces_numeric_string_for_experience_years():
    # Pydantic v2 coerces numeric strings for float fields by default
    profile = CandidateProfile(total_experience_years="3.5")
    assert profile.total_experience_years == 3.5


# ---------- null tolerance (LLMs emit null for empty fields) ----------

def test_null_end_date_for_current_job_is_accepted():
    from app.models.profile import CandidateProfile
    p = CandidateProfile.model_validate(
        {"full_time_periods": [{"role": "Engineer", "start": "2024-06", "end": None}]}
    )
    assert p.full_time_periods[0].end == ""


def test_null_scalar_and_list_fields_fall_back_to_defaults():
    from app.models.profile import CandidateProfile
    p = CandidateProfile.model_validate({
        "name": None, "career_level": None, "total_experience_years": None,
        "skills": None, "projects": [{"name": "X", "description": None}],
    })
    assert p.name is None
    assert p.career_level == "Unknown"
    assert p.total_experience_years == 0.0
    assert p.skills == []
    assert p.projects[0].description == ""


def test_period_without_start_is_still_rejected():
    import pytest
    from pydantic import ValidationError
    from app.models.profile import CandidateProfile
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate({"full_time_periods": [{"role": "x", "start": None}]})
