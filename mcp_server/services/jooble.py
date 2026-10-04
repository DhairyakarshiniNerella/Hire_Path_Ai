import requests

from mcp_server import config
from mcp_server.models import Job
from mcp_server.services._fields import as_text, items_from


def _normalize(raw: dict) -> Job:
    return Job(
        title=as_text(raw.get("title")),
        company=as_text(raw.get("company")),
        location=as_text(raw.get("location")),
        description=as_text(raw.get("snippet")),
        url=as_text(raw.get("link")),
        source="Jooble",
        source_id=as_text(raw.get("id")),
        employment_type=as_text(raw.get("type")) or "Unknown",
    )


def search(query: str, location: str = "", limit: int = 10) -> list[Job]:
    """Raises RuntimeError with a readable message if the API call fails."""
    if not config.JOOBLE_API_KEY:
        raise RuntimeError("Jooble API key is missing (set JOOBLE_API_KEY)")

    # The key is part of the URL, so never put the URL in an error message.
    url = "https://jooble.org/api/" + config.JOOBLE_API_KEY
    payload = {"keywords": query, "location": location}

    try:
        response = requests.post(url, json=payload, timeout=10)
    except requests.exceptions.Timeout:
        raise RuntimeError("Jooble request timed out")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error calling Jooble: {type(e).__name__}")

    if response.status_code in (401, 403):
        raise RuntimeError("Jooble rejected the API key")
    if response.status_code == 429:
        raise RuntimeError("Jooble rate limit reached, try again later")
    if response.status_code != 200:
        raise RuntimeError(f"Jooble returned status {response.status_code}")

    # Jooble has no "limit" parameter, so we trim after the call.
    return [_normalize(j) for j in items_from(response, "jobs", "Jooble")][:limit]
