import requests

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


def search_arbeitnow_jobs(query: str = "") -> dict:
    """
    Fetches jobs from Arbeitnow's public job board API (no API key needed)
    and filters them locally by the search query, since Arbeitnow doesn't
    support server-side keyword search.

    Returns: {"success": True, "jobs": [...raw Arbeitnow job dicts...]}
          or {"success": False, "error": "..."}
    """
    try:
        response = requests.get(ARBEITNOW_URL, timeout=10)

        if response.status_code == 429:
            return {"success": False, "error": "Arbeitnow rate limit reached, try again later"}
        if response.status_code != 200:
            return {"success": False, "error": f"Arbeitnow returned status {response.status_code}"}

        data = response.json()
        all_jobs = data.get("data", [])

        # Arbeitnow has no search parameter, so we filter locally by checking
        # if any individual word from the query (e.g. "Machine" or "Engineer"
        # from "Machine Learning Engineer") appears in the job title or tags.
        # Matching the whole phrase as one substring was too strict - "Machine
        # Learning Engineer" would never match a real posting titled
        # "Senior ML Engineer", so it silently returned zero jobs most of the time.
        query_words = [w for w in query.lower().split() if len(w) > 2]

        if query_words:
            filtered_jobs = [
                job for job in all_jobs
                if any(
                    word in job.get("title", "").lower()
                    or any(word in tag.lower() for tag in job.get("tags", []))
                    for word in query_words
                )
            ]
        else:
            filtered_jobs = all_jobs

        return {"success": True, "jobs": filtered_jobs}

    except requests.exceptions.Timeout:
        return {"success": False, "error": "Arbeitnow request timed out"}
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Network error calling Arbeitnow: {str(e)}"}
