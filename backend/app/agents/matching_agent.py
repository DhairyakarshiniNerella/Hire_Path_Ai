from typing import List
from app.services.matcher import calculate_match_score

# Jobs scoring below this are weak matches (missing most required skills,
# wrong experience level, etc.) - not worth surfacing as a "recommendation".
MIN_MATCH_SCORE = 40


def rank_jobs_for_candidate(candidate_profile, analyzed_jobs: List[dict]) -> List[dict]:
    """
    Scores every analyzed job against the candidate profile using our
    deterministic matcher, merges the scores into each job, drops jobs
    below MIN_MATCH_SCORE, and returns the rest sorted best-match-first.
    """
    scored_jobs = []

    for job in analyzed_jobs:
        score_result = calculate_match_score(candidate_profile, job)
        job.update(score_result)
        scored_jobs.append(job)

    ranked_jobs = [job for job in scored_jobs if job["match_score"] >= MIN_MATCH_SCORE]
    ranked_jobs.sort(key=lambda j: j["match_score"], reverse=True)
    return ranked_jobs
