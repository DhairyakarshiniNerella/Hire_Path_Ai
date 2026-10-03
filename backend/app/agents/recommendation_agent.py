from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.services.token_tracker import log_usage
from app.services.groq_client import build_structured_llm

load_dotenv()

# Only generate LLM explanations for the top N jobs, to keep costs/latency reasonable
TOP_N_RECOMMENDATIONS = 10


class JobExplanation(BaseModel):
    why_it_matches: str = Field(
        description="2-3 sentence explanation of why this job suits the candidate, "
        "referencing their actual matched skills/experience"
    )
    experience_analysis: str = Field(
        description="1-2 sentences explaining the experience compatibility result in plain language"
    )
    skill_gap_summary: str = Field(
        description="1-2 sentences summarizing missing skills and how much they matter, "
        "or noting there are none"
    )


# Automatically falls back to GROQ_API_KEY_2 if the primary key's quota is exhausted.
structured_llm = build_structured_llm(JobExplanation, temperature=0.3)

EXPLANATION_PROMPT = """You are a career advisor helping a candidate understand a job recommendation.

You are given the candidate's profile, a job posting, and PRE-CALCULATED matching data
that was computed deterministically. Do NOT change, recalculate, or contradict these numbers -
only explain them clearly and honestly. Do not invent skills, experience, or requirements
that are not in the data provided.
"""


def generate_recommendation(candidate_profile, job: dict) -> dict:
    """
    Takes one ranked job (already scored by the Matching Agent) and asks the LLM
    to explain the result in plain language. Falls back to a simple templated
    explanation if the LLM call fails, so the pipeline never crashes here.
    """
    try:
        context = f"""
Candidate:
- Skills: {', '.join(candidate_profile.skills)}
- Experience: {candidate_profile.total_experience_years} years ({candidate_profile.career_level})
- Target roles: {', '.join(candidate_profile.target_roles)}

Job:
- Title: {job.get('title')}
- Company: {job.get('company')}

Pre-calculated matching data (do not change these):
- Match score: {job.get('match_score')}%
- Matched skills: {', '.join(job.get('matched_skills', [])) or 'None'}
- Missing skills: {', '.join(job.get('missing_skills', [])) or 'None'}
- Experience compatibility: {job.get('experience_compatibility')}
- Experience gap: {job.get('experience_gap') or 'None'}
- Experience required by job: {job.get('experience_required')}
"""
        messages = [
            ("system", EXPLANATION_PROMPT),
            ("human", context),
        ]
        result = structured_llm.invoke(messages)
        log_usage("Recommendation Agent", result["raw"])

        if result["parsed"] is None:
            raise ValueError(f"Could not parse recommendation explanation: {result.get('parsing_error')}")

        explanation = result["parsed"]

        job["why_it_matches"] = explanation.why_it_matches
        job["experience_analysis"] = explanation.experience_analysis
        job["skill_gap_summary"] = explanation.skill_gap_summary

    except Exception:
        # Fall back to a simple, still-useful explanation instead of crashing
        job["why_it_matches"] = f"This job matched {job.get('match_score', 0)}% based on your skills and experience."
        job["experience_analysis"] = f"Experience compatibility: {job.get('experience_compatibility', 'Unknown')}."
        job["skill_gap_summary"] = (
            f"Missing skills: {', '.join(job.get('missing_skills', []))}"
            if job.get("missing_skills") else "No major skill gaps found."
        )

    return job


def generate_recommendations(candidate_profile, ranked_jobs: List[dict]) -> List[dict]:
    """Generates explanations for the top N ranked jobs only, to limit LLM calls."""
    top_jobs = ranked_jobs[:TOP_N_RECOMMENDATIONS]
    return [generate_recommendation(candidate_profile, job) for job in top_jobs]
