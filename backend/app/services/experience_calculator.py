import re
import math
from datetime import date
from typing import Iterable, Optional, Tuple


def _parse_month(value: str, today: date) -> Optional[Tuple[int, int]]:
    """Parses 'YYYY-MM' (or 'present'/'current'/empty = today) into (year, month)."""
    v = (value or "").strip().lower()
    if v in ("", "present", "current", "now", "till date", "ongoing"):
        return today.year, today.month
    try:
        year, month = v.split("-")[:2]
        year, month = int(year), int(month)
        if 1 <= month <= 12:
            return year, month
    except ValueError:
        pass
    return None


def calculate_full_time_years(periods: Iterable, today: Optional[date] = None) -> float:
    """
    Sums full-time employment periods in years, counting overlaps once and
    ignoring gaps between jobs. Result is rounded to the nearest 0.5.
    Each period needs .start and .end ('YYYY-MM', or empty/'Present' for current).
    """
    today = today or date.today()
    spans = []
    for p in periods:
        start = _parse_month(p.start, today)
        end = _parse_month(p.end, today)
        if start is None or end is None:
            continue
        s = start[0] * 12 + start[1]
        e = end[0] * 12 + end[1]
        e += 1  # months are inclusive: Jun 2024 - Jun 2024 is one month
        if e > s:
            spans.append((s, e))

    spans.sort()
    total_months = 0
    cur_start = cur_end = None
    for s, e in spans:
        if cur_end is None or s > cur_end:
            if cur_end is not None:
                total_months += cur_end - cur_start
            cur_start, cur_end = s, e
        else:
            cur_end = max(cur_end, e)
    if cur_end is not None:
        total_months += cur_end - cur_start

    return math.floor(total_months / 12 * 2 + 0.5) / 2  # half-up, not banker's rounding


def career_level_for(years: float) -> str:
    if years <= 0:
        return "Fresher"
    if years < 2:
        return "Entry Level"
    if years <= 5:
        return "Mid Level"
    return "Senior"


_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]

# Whole words only, so "internal"/"international" don't count as internships.
_INTERN_RE = re.compile(
    r"\b(?:intern(?:s|ship|ships)?|trainee(?:s|ship)?|apprentice(?:s|ship)?)\b", re.IGNORECASE
)
_BULLET_RE = re.compile(r"^\s*[•▪●◦*\-–—]\s")
# A line holding a year plus a range separator is another entry's (or the education's) date line.
_DATE_LINE_RE = re.compile(r"\b(?:19|20)\d{2}\b.*?(?:-|–|—|\bto\b)", re.IGNORECASE)
_HEADER_LINES_ABOVE = 3  # heading, job title and company can each sit on their own line


def _start_date_pattern(year: int, month: int) -> "re.Pattern":
    """Matches the start of a date range: 'Aug 2023 -', 'August, 2023 to', '08/2023 -', '2023-08 -'."""
    mon = _MONTHS[month - 1]
    forms = [
        rf"{mon}[a-z]*\.?,?\s*{year}",
        rf"\b0?{month}\s*[/.\-]\s*{year}",
        rf"\b{year}\s*[/.\-]\s*0?{month}\b",
    ]
    return re.compile(rf"(?:{'|'.join(forms)})\s*(?:-|–|—|to\b)", re.IGNORECASE)


def _entry_header(resume_text: str, match: "re.Match") -> str:
    """
    The header of the experience entry whose date range was matched: the date line plus up to
    a few lines above it, stopping at a bullet or at the previous entry's date line so the
    previous entry's text never leaks in.
    """
    lines_before = resume_text[: match.start()].split("\n")
    date_line = lines_before.pop() + resume_text[match.start():].split("\n", 1)[0]
    header = [date_line]
    for line in reversed(lines_before):
        if _BULLET_RE.match(line) or _DATE_LINE_RE.search(line):
            break
        header.append(line)
        if len(header) > _HEADER_LINES_ABOVE:
            break
    return "\n".join(header)


def is_internship_period(period, resume_text: str) -> bool:
    """
    True if this period is an internship/trainee stint. Checks the job title first, then the
    entry's own header in the resume (e.g. an 'Information Technology Internship' heading above
    'RPA Developer ... Aug 2023 - Jun 2024'), since the title itself often doesn't say 'intern'.
    """
    if _INTERN_RE.search(period.role or ""):
        return True
    try:
        year, month = (int(x) for x in period.start.strip().split("-")[:2])
        pattern = _start_date_pattern(year, month)
    except (ValueError, IndexError):
        return False
    return any(
        _INTERN_RE.search(_entry_header(resume_text, m))
        for m in pattern.finditer(resume_text or "")
    )
