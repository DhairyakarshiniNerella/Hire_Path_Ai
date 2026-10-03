import requests

from mcp_server import config
from mcp_server.models import Job


def _normalize(raw: dict) -> Job:
    return Job(
        title=raw.get("title", ""),
        company=raw.get("company", {}).get("display_name", ""),
        location=raw.get("location", {}).get("display_name", ""),
        description=raw.get("description", ""),
        url=raw.get("redirect_url", ""),
        source="Adzuna",
        source_id=str(raw.get("id", "")),
        employment_type=raw.get("contract_time") or "Unknown",
    )


def search(query: str, location: str = "", limit: int = 10) -> list[Job]:
    """Raises RuntimeError with a readable message if the API call fails."""
    if not config.ADZUNA_APP_ID or not config.ADZUNA_APP_KEY:
        raise RuntimeError("Adzuna API credentials are missing (set ADZUNA_APP_ID and ADZUNA_APP_KEY)")

    url = f"https://api.adzuna.com/v1/api/jobs/{config.ADZUNA_COUNTRY}/search/1"
    params = {
        "app_id": config.ADZUNA_APP_ID,
        "app_key": config.ADZUNA_APP_KEY,
        "what": query,
        "results_per_page": limit,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    try:
        response = requests.get(url, params=params, timeout=10)
    except requests.exceptions.Timeout:
        raise RuntimeError("Adzuna request timed out")
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Network error calling Adzuna: {type(e).__name__}")

    if response.status_code in (401, 403):
        raise RuntimeError("Adzuna rejected the API credentials")
    if response.status_code == 429:
        raise RuntimeError("Adzuna rate limit reached, try again later")
    if response.status_code != 200:
        raise RuntimeError(f"Adzuna returned status {response.status_code}")

    return [_normalize(j) for j in response.json().get("results", [])]
