import re

# Order matters: check the most specific patterns first, fall back to plainer ones.

RANGE_PATTERN = re.compile(r"(\d+)\s*(?:-|to|–)\s*(\d+)\+?\s*years?", re.IGNORECASE)
PLUS_PATTERN = re.compile(r"(\d+)\s*\+\s*years?", re.IGNORECASE)
MINIMUM_PATTERN = re.compile(r"(?:minimum|min\.?|at least)\s*(?:of\s*)?(\d+)\s*years?", re.IGNORECASE)
FRESHER_PATTERN = re.compile(
    r"\b(fresher|freshers|entry[\s-]?level|graduate|no experience required|no prior experience)\b",
    re.IGNORECASE,
)
PLAIN_YEARS_PATTERN = re.compile(r"(\d+)\s*years?", re.IGNORECASE)


def extract_experience_requirement(text: str) -> dict:
    """
    Scans job description text for an experience requirement phrase.
    Returns a structured, deterministic result - never guesses.

    Returns:
        {
            "raw_text": the exact phrase that matched, or "Unknown",
            "min_years": float or None,
            "max_years": float or None,
        }
    """
    if not text:
        return {"raw_text": "Unknown", "min_years": None, "max_years": None}

    # "3-5 years", "0-2 years"
    match = RANGE_PATTERN.search(text)
    if match:
        return {
            "raw_text": match.group(0).strip(),
            "min_years": float(match.group(1)),
            "max_years": float(match.group(2)),
        }

    # "3+ years", "1+ years"
    match = PLUS_PATTERN.search(text)
    if match:
        return {
            "raw_text": match.group(0).strip(),
            "min_years": float(match.group(1)),
            "max_years": None,
        }

    # "Minimum 2 years", "at least 2 years"
    match = MINIMUM_PATTERN.search(text)
    if match:
        return {
            "raw_text": match.group(0).strip(),
            "min_years": float(match.group(1)),
            "max_years": None,
        }

    # "Fresher", "Entry Level", "Graduate"
    match = FRESHER_PATTERN.search(text)
    if match:
        return {
            "raw_text": match.group(0).strip(),
            "min_years": 0.0,
            "max_years": 0.0,
        }

    # Plain "2 years", "0 years" (no +, no range, no "minimum")
    match = PLAIN_YEARS_PATTERN.search(text)
    if match:
        return {
            "raw_text": match.group(0).strip(),
            "min_years": float(match.group(1)),
            "max_years": float(match.group(1)),
        }

    # Nothing recognizable - be honest about it, don't guess
    return {"raw_text": "Unknown", "min_years": None, "max_years": None}
