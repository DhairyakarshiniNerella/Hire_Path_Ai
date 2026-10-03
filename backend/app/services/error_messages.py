import re


def friendly_agent_error(error: Exception) -> str:
    """
    Turns a raw exception - often a large, technical JSON blob straight from
    Groq's API - into one short sentence safe to show directly in the UI.
    Anything not specifically recognized falls back to a generic message,
    rather than ever showing raw API/JSON text to the user.
    """
    text = str(error)
    lower = text.lower()

    # Bare "429"/"401" substring checks are too easy to false-positive on
    # (a token count like "4019" or an org/request ID contains "401"/"429"
    # without meaning a 429/401 HTTP status at all) - \b anchors them to
    # the actual standalone number, not a digit sequence they're embedded in.
    has_429 = bool(re.search(r"\b429\b", text))
    has_401 = bool(re.search(r"\b401\b", text))

    if "rate_limit_exceeded" in lower or has_429:
        scope = "today's" if ("tokens per day" in lower or "(tpd)" in lower) else "the current"

        wait_match = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", text)
        if wait_match:
            minutes_part = int(wait_match.group(1)) if wait_match.group(1) else 0
            seconds_part = float(wait_match.group(2))
            total_seconds = minutes_part * 60 + seconds_part
            wait_text = "under a minute" if total_seconds < 60 else f"about {round(total_seconds / 60)} minute(s)"
            return f"We've hit {scope} usage limit for the AI service. Please try again in {wait_text}."

        return f"We've hit {scope} usage limit for the AI service. Please try again shortly."

    if has_401 or "invalid_api_key" in lower or "unauthorized" in lower or "authentication" in lower:
        return "The AI service rejected our credentials - this is a setup issue, not something caused by your resume. Please contact the site owner."

    if "did not call a tool" in lower:
        return "We couldn't find resume details in this file. Please upload a text-based PDF or DOCX of your resume (scanned images can't be read)."

    if "could not parse" in lower or "parsing_error" in lower or "tool_use_failed" in lower:
        return "We had trouble reading some details from your resume clearly. Please try again - if it keeps happening, try a simpler resume format (avoid tables/columns)."

    if "timed out" in lower or "timeout" in lower:
        return "The AI service took too long to respond. Please try again."

    if "connection" in lower or "network error" in lower:
        return "Couldn't reach the AI service - please check your connection and try again."

    return "Something went wrong while processing your request. Please try again in a moment."
