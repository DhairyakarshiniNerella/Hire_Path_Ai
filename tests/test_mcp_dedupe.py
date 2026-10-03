from mcp_server.dedupe import remove_duplicates
from mcp_server.models import Job


def make(title="Python Developer", company="Acme", location="Pune", source="Adzuna", source_id="1"):
    return Job(title=title, company=company, location=location, source=source, source_id=source_id)


def test_same_source_and_id_is_duplicate():
    jobs = [make(), make(title="Different title")]
    assert len(remove_duplicates(jobs)) == 1


def test_same_job_on_two_sources_is_duplicate_ignoring_case():
    jobs = [make(source="Adzuna", source_id="1"), make(title="python developer", source="Jooble", source_id="9")]
    result = remove_duplicates(jobs)
    assert len(result) == 1 and result[0].source == "Adzuna"


def test_different_jobs_are_kept():
    jobs = [make(source_id="1"), make(title="Data Engineer", source_id="2")]
    assert len(remove_duplicates(jobs)) == 2
