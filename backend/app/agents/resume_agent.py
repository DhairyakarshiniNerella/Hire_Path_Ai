import re
from datetime import date

from dotenv import load_dotenv
from app.models.profile import CandidateProfile
from app.services.experience_calculator import (
    calculate_full_time_years, career_level_for, is_internship_period,
)
from app.services.project_verifier import restore_project_names, restore_project_text
from app.services.token_tracker import log_usage
from app.services.groq_client import build_structured_llm

# Load GROQ_API_KEY (and optional GROQ_API_KEY_2) from the .env file
load_dotenv()

# Structured-output client for resume analysis, bound to CandidateProfile.
# include_raw=True also gives us the raw AIMessage (with token usage) alongside
# the parsed object, so we can track how many tokens this call actually cost.
# Automatically falls back to GROQ_API_KEY_2 if the primary key's quota is exhausted.
structured_llm = build_structured_llm(CandidateProfile, temperature=0)

# Instructions given to the LLM every time we analyze a resume
# {today} is filled in at call time so "Present"/"Current" entries resolve
# against the real date instead of the model's training cutoff.
SYSTEM_PROMPT_TEMPLATE = """You are a resume analysis expert.
Read the resume text and extract structured information about the candidate.
Today's date is {today}.

Rules:
- If information is not present in the resume, leave it empty or use the field's default. Never invent details.
- total_experience_years counts FULL-TIME employment only. Internships, trainee/apprentice
  stints, and freelance/academic projects must NOT be counted (they still go in the
  "internships" / "experience" lists as appropriate). Gaps between jobs (time not employed)
  are NOT counted either. Do not stop at the first role you find.
  Steps:
    1. Find every FULL-TIME role with a start date and an end date (or "Present"/"Current"/
       "Till date", which means today's date, {today}). Skip internships.
    2. Convert each role's span to years (round to the nearest 0.5 e.g. 3 months ~= 0.25 years).
    3. If two full-time roles' dates overlap, count the overlapping span once, not twice.
    4. Sum only those spans - never the calendar time from the first job to the last. A role
       still marked "Present" must be counted all the way up to {today}.
  Also list every full-time role's dates in full_time_periods (start/end as YYYY-MM, end empty
  if current, plus the job title in "role") - the server recomputes the total from these, so they
  must be accurate. NEVER put an internship in full_time_periods.
  Example: 5-month internship, 1-year gap, 2.5-year full-time job, 1-year gap, 1-year
  full-time job => total_experience_years = 3.5 (2.5 + 1; internship and gaps excluded).
  If the candidate has only internships, total_experience_years = 0.
- career_level should be one of: Fresher, Entry Level, Mid Level, Senior, Unknown - based on the
  computed total_experience_years (0 = Fresher, <2 = Entry Level, 2-5 = Mid Level, >5 = Senior).
- target_roles should be 2-4 job titles the candidate is realistically suited for, based on their skills and experience.
- projects: include every entry from the resume's Projects section, AND any project that is
  explicitly described as a project inside the Experience/Internship section (e.g. a bullet that
  names a specific project, POC, or product/module the candidate built, such as "Built a Leave
  Management API POC"). Do not turn ordinary responsibilities (testing, optimizing queries,
  configuring tools, migrating bots) into projects, and list each project only once. If neither
  place has any, return an empty projects list.
- For projects, copy the project "name" EXACTLY as written in the resume (same words, spelling and
  capitalization - never rename, shorten, or rephrase it) and copy its "description" EXACTLY as
  written too, verbatim, without rewording or summarizing. Do not add, invent, or merge anything,
  and do not attach a description from a different project. For a project taken from an
  Experience bullet, the name is the exact phrase from that bullet (e.g. "Leave Management API POC")
  and the description is that whole bullet, verbatim. Only if the resume gives a description
  with no title at all, create a short name from it.
"""


# Total tries when the model's output can't be parsed into a CandidateProfile.
PARSE_ATTEMPTS = 3


def analyze_resume(resume_text: str) -> CandidateProfile:
    """
    Sends resume text to the Groq LLM and returns a structured CandidateProfile.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(today=date.today().isoformat())
    messages = [
        ("system", system_prompt),
        ("human", f"Resume text:\n\n{resume_text}"),
    ]
    # The model occasionally returns output that doesn't fit the schema; a fresh attempt
    # nearly always succeeds, so retry before giving up.
    for _ in range(PARSE_ATTEMPTS):
        result = structured_llm.invoke(messages)
        log_usage("Resume Analyzer Agent", result["raw"])
        if result["parsed"] is not None:
            break

    if result["parsed"] is None:
        raise ValueError(f"Could not parse resume into a profile: {result.get('parsing_error')}")

    profile = result["parsed"]

    # LLMs are unreliable at date arithmetic, so recompute from the extracted dates.
    # Drop internships/trainee stints even if the model listed them by mistake.
    # (Checked against the resume text too, since an internship's job title often
    # doesn't say "intern", e.g. "RPA Developer" under an "Internship" heading.)
    listed = profile.full_time_periods
    profile.full_time_periods = [p for p in listed if not is_internship_period(p, resume_text)]
    if listed:
        profile.total_experience_years = calculate_full_time_years(profile.full_time_periods)
        profile.career_level = career_level_for(profile.total_experience_years)

    restore_project_text(profile.projects, resume_text)
    restore_project_names(profile.projects, resume_text)

    return profile
