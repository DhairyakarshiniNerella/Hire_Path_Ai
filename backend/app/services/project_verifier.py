import re
from typing import List

BULLET_SPLIT = re.compile(r"\n\s*[•●▪◦\-*]\s*")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _words(text: str) -> set:
    return set(re.findall(r"[a-z0-9+#.]+", text.lower()))


def _segments(resume_text: str) -> List[str]:
    """Splits the resume into bullet-sized chunks, joining lines wrapped inside a bullet."""
    return [s for s in (_norm(p) for p in BULLET_SPLIT.split("\n" + resume_text)) if s]


def restore_project_text(projects: list, resume_text: str) -> list:
    """
    Guarantees each project's description is text that really appears in the resume.
    If the model paraphrased it, replace it with the resume segment it most resembles.
    """
    flat = _norm(resume_text).lower()
    segments = _segments(resume_text)

    for project in projects:
        desc = _norm(project.description)
        if not desc or desc.lower() in flat:
            continue
        desc_words = _words(desc)
        best, best_score = None, 0.0
        for seg in segments:
            seg_words = _words(seg)
            if not seg_words:
                continue
            score = len(desc_words & seg_words) / len(desc_words | seg_words)
            if score > best_score:
                best, best_score = seg, score
        if best and best_score >= 0.25:
            project.description = best
    return projects


def _find_exact(name: str, text: str):
    """Finds `name` in `text` ignoring case/whitespace; returns the text as the resume wrote it."""
    pattern = r"\s+".join(re.escape(w) for w in name.split())
    m = re.search(pattern, text, re.IGNORECASE) if pattern else None
    return m.group(0) if m else None


def restore_project_names(projects: list, resume_text: str) -> list:
    """
    Guarantees each project name is the wording the resume itself uses.
    Exact matches are re-cased to the resume's spelling; a name the model made up
    is replaced by the closest run of words in the project's own resume bullet
    (or anywhere in the resume if the bullet can't be found).
    """
    flat = _norm(resume_text)
    for project in projects:
        name = _norm(project.name)
        if not name:
            continue
        exact = _find_exact(name, flat)
        if exact:
            project.name = exact
            continue

        haystack = _norm(project.description) if project.description else ""
        if haystack.lower() not in flat.lower():
            haystack = flat
        tokens = haystack.split()
        name_words = _words(name)
        size = len(name.split())
        best, best_score = None, 0.0
        for n in range(max(1, size - 1), size + 2):
            for i in range(len(tokens) - n + 1):
                span = tokens[i:i + n]
                span_words = _words(" ".join(span))
                if not span_words:
                    continue
                score = len(name_words & span_words) / len(name_words | span_words)
                if score > best_score:
                    best, best_score = span, score
        if best and best_score >= 0.5:
            project.name = " ".join(best).strip(" ,.;:-()")
    return projects
