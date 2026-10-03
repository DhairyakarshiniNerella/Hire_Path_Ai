import requests

from mcp_server.models import Job

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def _normalize(raw: dict) -> Job:
    return Job(
        title=raw.get("title", ""),
        company=raw.get("company_name", ""),
        location=raw.get("location", ""),
        description=raw.get("description", ""),
        url=raw.get("url", ""),
        source="Arbeitnow",
        source_id=raw.get("slug", ""),
        employment_type=", ".join(raw.get("job_types", [])) or "Unknown",
    )


def search(query: str, location: str = "") -> list[Job]:
    """
    Fetches Arbeitnow jobs (no API key needed) and filters them locally,
    because Arbeitnow has no server-side keyword search.
    Raises RuntimeError with a readable message if the API call fails.
    """
    try:
        response = requests.get(ARBEITNOW_URL, timeout=10)
    except requests.exceptions.Timeout:
        raise RuntimeError("Arbeitnow request timed out")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error calling Arbeitnow: {e}")

    if response.status_code == 429:
        raise RuntimeError("Arbeitnow rate limit reached, try again later")
    if response.status_code != 200:
        raise RuntimeError(f"Arbeitnow returned status {response.status_code}")

    raw_jobs = response.json().get("data", [])

    # Match if ANY word of the query appears in the title or tags
    # (same rule as the original HirePath arbeitnow_tool.py).
    words = [w for w in query.lower().split() if len(w) > 2]
    if words:
        raw_jobs = [
            j for j in raw_jobs
            if any(
                w in j.get("title", "").lower()
                or any(w in t.lower() for t in j.get("tags", []))
                for w in words
            )
        ]

    # Arbeitnow has no location filter either, so filter by text when given.
    if location:
        loc = location.lower()
        raw_jobs = [j for j in raw_jobs if loc in j.get("location", "").lower()]

    return [_normalize(j) for j in raw_jobs]
