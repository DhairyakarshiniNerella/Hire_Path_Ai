from mcp_server.models import Job


def _clean(value: str) -> str:
    return (value or "").strip().lower()


def remove_duplicates(jobs: list[Job]) -> list[Job]:
    """
    Drops repeated jobs, keeping the first one seen. Two checks (same rules as the
    original HirePath job_normalizer.py):
    1. same source + same source_id -> the exact same listing twice
    2. same title + company + location -> the same real job posted on two sources
    """
    seen_ids = set()
    seen_content = set()
    unique = []

    for job in jobs:
        id_key = (job.source, job.source_id)
        content_key = (_clean(job.title), _clean(job.company), _clean(job.location))

        if (job.source_id and id_key in seen_ids) or content_key in seen_content:
            continue

        if job.source_id:
            seen_ids.add(id_key)
        seen_content.add(content_key)
        unique.append(job)

    return unique
