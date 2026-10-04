"""Helpers for reading job-API responses, which may send null, numbers or odd shapes."""


def as_text(value, default: str = "") -> str:
    """A string for any API value: None -> default, numbers and other types -> str()."""
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def items_from(response, key: str, source: str) -> list[dict]:
    """The list of job dicts under `key` in a JSON response, or a readable RuntimeError."""
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"{source} returned an unreadable response")
    if not isinstance(payload, dict):
        raise RuntimeError(f"{source} returned an unexpected response")
    return [item for item in as_list(payload.get(key)) if isinstance(item, dict)]
