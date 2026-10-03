import os
import requests
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY")

# "in" = India. Change this if you want to search a different country.
ADZUNA_COUNTRY = "in"
ADZUNA_BASE_URL = f"https://api.adzuna.com/v1/api/jobs/{ADZUNA_COUNTRY}/search/1"


def search_adzuna_jobs(query: str, location: str = "", results_per_page: int = 10) -> dict:
    """
    Searches Adzuna for jobs matching the query.
    Returns: {"success": True, "jobs": [...raw Adzuna job dicts...]}
          or {"success": False, "error": "..."}
    """
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return {"success": False, "error": "Adzuna API credentials are missing. Check your .env file."}

    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "what": query,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }
    if location:
        params["where"] = location

    try:
        response = requests.get(ADZUNA_BASE_URL, params=params, timeout=10)

        if response.status_code == 401:
            return {"success": False, "error": "Adzuna rejected the API credentials"}
        if response.status_code == 429:
            return {"success": False, "error": "Adzuna rate limit reached, try again later"}
        if response.status_code != 200:
            return {"success": False, "error": f"Adzuna returned status {response.status_code}"}

        data = response.json()
        jobs = data.get("results", [])
        return {"success": True, "jobs": jobs}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Adzuna request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Network error calling Adzuna: {str(e)}"}
