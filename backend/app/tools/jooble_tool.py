import os
import requests
from dotenv import load_dotenv

load_dotenv()

JOOBLE_API_KEY = os.getenv("JOOBLE_API_KEY")
JOOBLE_BASE_URL = "https://jooble.org/api/"


def search_jooble_jobs(query: str, location: str = "") -> dict:
    """
    Searches Jooble for jobs matching the query.
    Returns: {"success": True, "jobs": [...raw Jooble job dicts...]}
          or {"success": False, "error": "..."}
    """
    if not JOOBLE_API_KEY:
        return {"success": False, "error": "Jooble API key is missing. Check your .env file."}

    url = JOOBLE_BASE_URL + JOOBLE_API_KEY

    # Jooble takes the search as a JSON body, not query params
    payload = {
        "keywords": query,
        "location": location,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)

        if response.status_code == 401:
            return {"success": False, "error": "Jooble rejected the API key"}
        if response.status_code == 429:
            return {"success": False, "error": "Jooble rate limit reached, try again later"}
        if response.status_code != 200:
            return {"success": False, "error": f"Jooble returned status {response.status_code}"}

        data = response.json()
        jobs = data.get("jobs", [])
        return {"success": True, "jobs": jobs}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Jooble request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Network error calling Jooble: {str(e)}"}
