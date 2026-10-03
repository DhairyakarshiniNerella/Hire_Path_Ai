from typing import List
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.services.token_tracker import log_usage
from app.services.groq_client import build_structured_llm

load_dotenv()


class JobRequirements(BaseModel):
    required_skills: List[str] = Field(
        default_factory=list,
        description="Skills explicitly required or strongly implied by the job description"
    )
    preferred_skills: List[str] = Field(
        default_factory=list,
        description="Skills mentioned as 'nice to have', 'preferred', or 'bonus'"
    )
    education_requirement: str = Field(
        default="Unknown",
        description="Minimum education mentioned (e.g. 'Bachelor's in CS'), or 'Unknown' if not stated"
    )
    role: str = Field(
        default="Unknown",
        description="The general role category, e.g. 'Backend Developer', 'Data Scientist'"
    )
    technologies: List[str] = Field(
        default_factory=list,
        description="Specific tools/technologies mentioned, e.g. Docker, AWS, React"
    )
    responsibilities: List[str] = Field(
        default_factory=list,
        description="2-5 short bullet points summarizing what the person will actually do"
    )


# Automatically falls back to GROQ_API_KEY_2 if the primary key's quota is exhausted.
structured_llm = build_structured_llm(JobRequirements, temperature=0)

ANALYSIS_PROMPT = """You are a job description analysis expert.
Read the job posting below and extract its real requirements.

Rules:
- Only extract what is actually stated or clearly implied in the text. Never invent requirements.
- If a field is not mentioned, leave it empty or use 'Unknown'.
- Do NOT include years of experience in required_skills - that is handled separately.
"""


def analyze_job(job: dict) -> dict:
    """
    Takes one normalized job dict, extracts its requirements using the LLM,
    and merges the results into the job dict. Never crashes the pipeline -
    if analysis fails for one job, it's returned with an 'analysis_error' note instead.
    """
    try:
        messages = [
            ("system", ANALYSIS_PROMPT),
            ("human", f"Job Title: {job.get('title', '')}\n\nDescription:\n{job.get('description', '')[:3000]}"),
        ]
        result = structured_llm.invoke(messages)
        log_usage("Job Analysis Agent", result["raw"])

        if result["parsed"] is None:
            raise ValueError(f"Could not parse job requirements: {result.get('parsing_error')}")

        requirements = result["parsed"]

        job["required_skills"] = requirements.required_skills
        job["preferred_skills"] = requirements.preferred_skills
        job["skills_required"] = requirements.required_skills + requirements.preferred_skills
        job["education_requirement"] = requirements.education_requirement
        job["role"] = requirements.role
        job["technologies"] = requirements.technologies
        job["responsibilities"] = requirements.responsibilities

    except Exception as e:
        job["analysis_error"] = f"Job Analysis Agent failed: {str(e)}"

    return job


def analyze_jobs(jobs: List[dict]) -> List[dict]:
    """Runs analyze_job on a whole list of normalized jobs."""
    return [analyze_job(job) for job in jobs]
