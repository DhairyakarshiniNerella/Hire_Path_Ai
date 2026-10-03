from typing import List, Optional


def normalize_adzuna_job(job: dict) -> dict:
    return {
        "title": job.get("title", ""),
        "company": job.get("company", {}).get("display_name", ""),
        "location": job.get("location", {}).get("display_name", ""),
        "description": job.get("description", ""),
        "url": job.get("redirect_url", ""),
        "source": "Adzuna",
        "source_id": job.get("id", ""),
        "experience_required": "Unknown",  # extracted later by the Job Analysis Agent
        "skills_required": [],             # extracted later by the Job Analysis Agent
        "employment_type": job.get("contract_time", "Unknown"),
    }


def normalize_jooble_job(job: dict) -> dict:
    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "description": job.get("snippet", ""),
        "url": job.get("link", ""),
        "source": "Jooble",
        "source_id": str(job.get("id", "")),
        "experience_required": "Unknown",
        "skills_required": [],
        "employment_type": job.get("type", "Unknown"),
    }


def normalize_arbeitnow_job(job: dict) -> dict:
    return {
        "title": job.get("title", ""),
        "company": job.get("company_name", ""),
        "location": job.get("location", ""),
        "description": job.get("description", ""),
        "url": job.get("url", ""),
        "source": "Arbeitnow",
        "source_id": job.get("slug", ""),
        "experience_required": "Unknown",
        "skills_required": [],
        "employment_type": ", ".join(job.get("job_types", [])) or "Unknown",
    }


# Maps the "_source" tag the Job Search Agent added to the right normalizer function
NORMALIZERS = {
    "adzuna": normalize_adzuna_job,
    "jooble": normalize_jooble_job,
    "arbeitnow": normalize_arbeitnow_job,
}


def normalize_job(job: dict) -> Optional[dict]:
    """Normalizes a single raw job dict based on its '_source' tag. Returns None if unrecognized."""
    source = job.get("_source")
    normalizer = NORMALIZERS.get(source)
    if not normalizer:
        return None
    return normalizer(job)


def normalize_jobs(jobs: List[dict]) -> List[dict]:
    """Normalizes a list of raw jobs from any mix of sources, skipping ones we can't recognize."""
    normalized = []
    for job in jobs:
        result = normalize_job(job)
        if result is not None:
            normalized.append(result)
    return normalized


def _clean_text(value: str) -> str:
    """Lowercases and trims text so minor formatting differences don't block a duplicate match."""
    return (value or "").strip().lower()


def remove_duplicate_jobs(jobs: List[dict]) -> List[dict]:
    """
    Removes duplicate jobs using two checks:
    1. Same source + same source_id -> the exact same listing showed up from
       two different search queries (e.g. "Python Developer" and "Data Engineer"
       both matched the same Adzuna posting).
    2. Same title + company + location (case-insensitive) -> the same real-world
       job was posted on two different sources with different IDs.
    """
    seen_source_ids = set()
    seen_content_keys = set()
    unique_jobs = []

    for job in jobs:
        source_id_key = (job.get("source"), job.get("source_id"))
        content_key = (
            _clean_text(job.get("title")),
            _clean_text(job.get("company")),
            _clean_text(job.get("location")),
        )

        is_duplicate = False

        if job.get("source_id") and source_id_key in seen_source_ids:
            is_duplicate = True
        if content_key in seen_content_keys:
            is_duplicate = True

        if is_duplicate:
            continue

        if job.get("source_id"):
            seen_source_ids.add(source_id_key)
        seen_content_keys.add(content_key)
        unique_jobs.append(job)

    return unique_jobs


def select_balanced_jobs(jobs: List[dict], limit: int) -> List[dict]:
    """
    Picks up to `limit` jobs, round-robining across sources instead of
    taking a straight positional slice. Adzuna is always queried first for
    every search term, so a plain jobs[:limit] slice can end up entirely
    Adzuna even when Jooble/Arbeitnow also returned relevant results -
    this guarantees every source gets a turn before any source gets a second pick.
    """
    jobs_by_source: dict = {}
    source_order = []

    for job in jobs:
        source = job.get("source", "Unknown")
        if source not in jobs_by_source:
            jobs_by_source[source] = []
            source_order.append(source)
        jobs_by_source[source].append(job)

    selected = []
    round_index = 0
    while len(selected) < limit and any(jobs_by_source[s] for s in source_order):
        source = source_order[round_index % len(source_order)]
        if jobs_by_source[source]:
            selected.append(jobs_by_source[source].pop(0))
        round_index += 1

    return selected
