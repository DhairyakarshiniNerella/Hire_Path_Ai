from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class NullTolerantModel(BaseModel):
    """
    LLMs often emit null for fields they have nothing for (e.g. "end": null for a
    current job), which fails validation on non-Optional fields and aborts the whole
    resume analysis. Dropping null values lets each field fall back to its default.
    """

    @model_validator(mode="before")
    @classmethod
    def _drop_nulls(cls, data):
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
        return data


class ProjectEntry(NullTolerantModel):
    """
    One project from the candidate's resume, split into a short name and a
    separate description - so the frontend can highlight the name distinctly
    instead of guessing where it ends inside a paragraph of text.
    """

    name: str = Field(description="Project title copied exactly as written in the resume")
    description: str = Field(
        default="",
        description="Project description copied verbatim from the resume"
    )


class EmploymentPeriod(NullTolerantModel):
    """One FULL-TIME job's dates. Used to compute experience deterministically."""

    role: str = Field(default="", description="Job title exactly as written, e.g. 'Programmer/Analyst - II'")
    start: str = Field(description="Start month as YYYY-MM, e.g. '2024-06'")
    end: str = Field(default="", description="End month as YYYY-MM, or empty if the role is current (Present)")


class CandidateProfile(NullTolerantModel):
    """
    Structured information extracted from a candidate's resume.
    The Resume Analyzer Agent will fill this in using the Groq LLM.
    """

    name: Optional[str] = Field(default=None, description="Candidate's full name")
    email: Optional[str] = Field(default=None, description="Candidate's email address")

    education: List[str] = Field(
        default_factory=list,
        description="Degrees, institutions, and graduation years"
    )

    skills: List[str] = Field(
        default_factory=list,
        description="Technical and soft skills, e.g. Python, SQL, Communication"
    )

    projects: List[ProjectEntry] = Field(
        default_factory=list,
        description="Notable projects, each with a short name and description"
    )

    internships: List[str] = Field(
        default_factory=list,
        description="Internship roles and companies"
    )

    experience: List[str] = Field(
        default_factory=list,
        description="Work experience entries (role, company, duration, responsibilities)"
    )

    full_time_periods: List[EmploymentPeriod] = Field(
        default_factory=list,
        description="Dates of each FULL-TIME job only (exclude internships)"
    )

    total_experience_years: float = Field(
        default=0.0,
        description="Total years of FULL-TIME experience only (no internships, no employment gaps). 0 for freshers."
    )

    job_titles: List[str] = Field(
        default_factory=list,
        description="Previous job titles held"
    )

    companies: List[str] = Field(
        default_factory=list,
        description="Companies the candidate has worked at"
    )

    technologies: List[str] = Field(
        default_factory=list,
        description="Specific tools/technologies used, e.g. Docker, AWS, React"
    )

    career_level: str = Field(
        default="Unknown",
        description="e.g. Fresher, Entry Level, Mid Level, Senior"
    )

    target_roles: List[str] = Field(
        default_factory=list,
        description="Roles the candidate seems suited for or is targeting"
    )
