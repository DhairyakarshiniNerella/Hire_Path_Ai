from app.services.experience_parser import extract_experience_requirement
from app.services.embeddings import compute_semantic_similarity


def check_experience_compatibility(candidate_years: float, job_min_years, job_max_years, job_raw_text: str) -> dict:
    """
    Compares the candidate's experience against a job's parsed requirement.

    Returns:
        {
            "experience_compatibility": "Compatible" | "Low" | "Overqualified" | "Unknown",
            "experience_gap": a short explanation string, or None if there's no gap
        }
    """
    # The job posting didn't state a clear experience requirement -
    # be honest about it instead of guessing
    if job_min_years is None:
        return {
            "experience_compatibility": "Unknown",
            "experience_gap": None,
        }

    # Candidate meets or exceeds the minimum
    if candidate_years >= job_min_years:
        # If there's an upper bound and the candidate is well past it,
        # flag it so the candidate knows this role may be too junior for them
        if job_max_years is not None and candidate_years > job_max_years + 3:
            return {
                "experience_compatibility": "Overqualified",
                "experience_gap": f"This role expects {job_raw_text}, you may be more experienced than typical candidates.",
            }
        return {
            "experience_compatibility": "Compatible",
            "experience_gap": None,
        }

    # Candidate doesn't meet the minimum
    gap_years = job_min_years - candidate_years
    return {
        "experience_compatibility": "Low",
        "experience_gap": f"Requires {job_raw_text}, you currently have {candidate_years:g} year(s)",
    }


def _normalize_skill(skill: str) -> str:
    return skill.strip().lower()


def _skill_matches_any(target_skill_normalized: str, candidate_skills_normalized: set) -> bool:
    """True if target_skill matches any candidate skill exactly, or as a substring either way."""
    for candidate_skill in candidate_skills_normalized:
        if target_skill_normalized == candidate_skill:
            return True
        if target_skill_normalized in candidate_skill or candidate_skill in target_skill_normalized:
            return True
    return False


def match_skills(candidate_skills: list, job_required_skills: list, job_preferred_skills: list = None) -> dict:
    """
    Compares candidate skills against a job's required/preferred skills.

    Returns:
        {
            "matched_skills": [...skills the candidate has that the job wants...],
            "missing_skills": [...required skills the candidate is missing...],
            "skill_match_score": 0.0 to 1.0
        }
    """
    job_preferred_skills = job_preferred_skills or []

    candidate_normalized = {_normalize_skill(s) for s in candidate_skills}
    required_normalized = {_normalize_skill(s): s for s in job_required_skills}
    preferred_normalized = {_normalize_skill(s): s for s in job_preferred_skills}
    all_job_skills = {**required_normalized, **preferred_normalized}  # required wins on key collision

    matched_skills = [
        original for norm, original in all_job_skills.items()
        if _skill_matches_any(norm, candidate_normalized)
    ]

    missing_skills = [
        original for norm, original in required_normalized.items()
        if not _skill_matches_any(norm, candidate_normalized)
    ]

    # Score is based on required skills primarily; if the job listed none,
    # fall back to preferred skills so we don't unfairly zero out the score.
    score_basis = required_normalized if required_normalized else preferred_normalized

    if score_basis:
        matched_count = sum(1 for norm in score_basis if _skill_matches_any(norm, candidate_normalized))
        skill_match_score = matched_count / len(score_basis)
    else:
        skill_match_score = 0.0

    return {
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "skill_match_score": round(skill_match_score, 2),
    }


WEIGHTS = {
    "skill": 0.35,
    "experience": 0.25,
    "role": 0.20,
    "project": 0.10,
    "education": 0.10,
}


def _rescale_similarity(raw_score: float, floor: float = 0.1, ceiling: float = 0.7) -> float:
    """
    Raw cosine similarity from MiniLM embeddings sits in a compressed band
    (roughly 0.1-0.7 for related text, as we saw in Step 29), not a clean 0-1
    range. This rescales it into an intuitive 0-1 contribution for our score.
    """
    if raw_score <= floor:
        return 0.0
    if raw_score >= ceiling:
        return 1.0
    return (raw_score - floor) / (ceiling - floor)


def _experience_score(compatibility: str) -> float:
    return {
        "Compatible": 1.0,
        "Overqualified": 0.8,
        "Unknown": 0.6,
        "Low": 0.2,
    }.get(compatibility, 0.5)


def _match_education(candidate_education: list, job_education_requirement: str) -> float:
    """Simple rule-based check: does any candidate education entry mention the job's stated requirement?"""
    if not job_education_requirement or job_education_requirement.strip().lower() == "unknown":
        return 0.7  # job didn't specify - don't penalize

    if not candidate_education:
        return 0.3  # job wants something specific, we don't know candidate's education

    keywords = ["bachelor", "master", "phd", "b.tech", "m.tech", "degree", "diploma", "b.sc", "m.sc"]
    job_req_lower = job_education_requirement.lower()
    candidate_text = " ".join(candidate_education).lower()

    if any(kw in job_req_lower and kw in candidate_text for kw in keywords):
        return 1.0
    return 0.5


def calculate_match_score(candidate_profile, job: dict) -> dict:
    """
    Combines skill matching, experience compatibility, role similarity,
    project relevance, and education match into one weighted score (0-100).
    Every number here comes from deterministic Python logic - no LLM involved.
    """
    # --- Skill match (35%) ---
    skill_result = match_skills(
        candidate_profile.skills,
        job.get("required_skills") or job.get("skills_required", []),
        job.get("preferred_skills", []),
    )

    # --- Experience match (25%) ---
    exp_requirement = extract_experience_requirement(job.get("description", ""))
    exp_result = check_experience_compatibility(
        candidate_profile.total_experience_years,
        exp_requirement["min_years"],
        exp_requirement["max_years"],
        exp_requirement["raw_text"],
    )
    experience_score = _experience_score(exp_result["experience_compatibility"])

    # --- Role match (20%) - semantic similarity between candidate's roles and the job title/role ---
    candidate_roles_text = ", ".join(candidate_profile.target_roles + candidate_profile.job_titles) or "Unknown"
    job_role_text = f"{job.get('title', '')} {job.get('role', '')}".strip() or "Unknown"
    role_raw_similarity = compute_semantic_similarity(candidate_roles_text, job_role_text)
    role_score = _rescale_similarity(role_raw_similarity)

    # --- Project match (10%) - semantic similarity between candidate's projects and the job description ---
    if candidate_profile.projects:
        candidate_projects_text = ", ".join(
            f"{p.name}: {p.description}" for p in candidate_profile.projects
        )
        project_raw_similarity = compute_semantic_similarity(candidate_projects_text, job.get("description", ""))
        project_score = _rescale_similarity(project_raw_similarity)
    else:
        project_score = 0.5  # no projects listed - neutral, don't penalize heavily

    # --- Education match (10%) ---
    education_score = _match_education(candidate_profile.education, job.get("education_requirement", "Unknown"))

    # --- Combine into final weighted score ---
    final_score = (
        skill_result["skill_match_score"] * WEIGHTS["skill"]
        + experience_score * WEIGHTS["experience"]
        + role_score * WEIGHTS["role"]
        + project_score * WEIGHTS["project"]
        + education_score * WEIGHTS["education"]
    )

    return {
        "match_score": round(final_score * 100),
        "matched_skills": skill_result["matched_skills"],
        "missing_skills": skill_result["missing_skills"],
        "skill_match_score": skill_result["skill_match_score"],
        "experience_compatibility": exp_result["experience_compatibility"],
        "experience_gap": exp_result["experience_gap"],
        "experience_required": exp_requirement["raw_text"],
        "role_match_score": round(role_score, 2),
        "project_match_score": round(project_score, 2),
        "education_match_score": round(education_score, 2),
    }
