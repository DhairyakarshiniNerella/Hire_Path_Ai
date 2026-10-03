from typing import TypedDict, List, Optional
from app.models.profile import CandidateProfile


class WorkflowState(TypedDict):
    """
    The shared state that flows through every agent in our LangGraph workflow.
    Each agent reads what it needs and writes its results back into this same object.
    """

    # Set at the start, by Flask
    resume_text: str

    # Filled in by the Resume Analyzer Agent
    candidate_profile: Optional[CandidateProfile]

    # Filled in by the Job Search Agent
    search_queries: List[str]
    jobs: List[dict]  # raw + normalized job postings from Adzuna/Jooble

    # Filled in by the Job Analysis Agent
    analyzed_jobs: List[dict]  # jobs with extracted requirements (skills, experience, etc.)

    # Filled in by the Matching Agent
    ranked_jobs: List[dict]  # analyzed_jobs with match scores, sorted best-first

    # Filled in by the Recommendation Agent
    recommendations: List[dict]  # final output shown to the user, with explanations

    # Any agent can append here if something goes wrong, instead of crashing the whole workflow
    errors: List[str]

    # Tracks which agent is currently running, so the frontend can show live progress
    current_agent: str
