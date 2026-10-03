from app.services.job_normalizer import (
    normalize_adzuna_job,
    normalize_jooble_job,
    normalize_arbeitnow_job,
    normalize_job,
    normalize_jobs,
    remove_duplicate_jobs,
    select_balanced_jobs,
)


def test_normalize_adzuna_job_full():
    raw = {
        "title": "Python Developer",
        "company": {"display_name": "Acme Corp"},
        "location": {"display_name": "Bangalore"},
        "description": "Build things",
        "redirect_url": "https://adzuna.example/job/1",
        "id": "123",
        "contract_time": "full_time",
    }
    result = normalize_adzuna_job(raw)
    assert result["title"] == "Python Developer"
    assert result["company"] == "Acme Corp"
    assert result["location"] == "Bangalore"
    assert result["source"] == "Adzuna"
    assert result["source_id"] == "123"
    assert result["employment_type"] == "full_time"
    assert result["skills_required"] == []
    assert result["experience_required"] == "Unknown"


def test_normalize_adzuna_job_missing_fields():
    result = normalize_adzuna_job({})
    assert result["title"] == ""
    assert result["company"] == ""
    assert result["location"] == ""
    assert result["employment_type"] == "Unknown"


def test_normalize_jooble_job_full():
    raw = {
        "title": "Data Analyst",
        "company": "Beta LLC",
        "location": "Remote",
        "snippet": "Analyze data",
        "link": "https://jooble.example/job/2",
        "id": 456,
        "type": "Contract",
    }
    result = normalize_jooble_job(raw)
    assert result["title"] == "Data Analyst"
    assert result["description"] == "Analyze data"
    assert result["source"] == "Jooble"
    assert result["source_id"] == "456"  # cast to str
    assert result["employment_type"] == "Contract"


def test_normalize_jooble_job_missing_fields():
    result = normalize_jooble_job({})
    assert result["source_id"] == ""
    assert result["employment_type"] == "Unknown"


def test_normalize_arbeitnow_job_full():
    raw = {
        "title": "Backend Engineer",
        "company_name": "Gamma Inc",
        "location": "Berlin",
        "description": "Build APIs",
        "url": "https://arbeitnow.example/job/3",
        "slug": "backend-engineer-gamma",
        "job_types": ["full_time", "remote"],
    }
    result = normalize_arbeitnow_job(raw)
    assert result["company"] == "Gamma Inc"
    assert result["source"] == "Arbeitnow"
    assert result["source_id"] == "backend-engineer-gamma"
    assert result["employment_type"] == "full_time, remote"


def test_normalize_arbeitnow_job_no_job_types():
    result = normalize_arbeitnow_job({"title": "X"})
    assert result["employment_type"] == "Unknown"


def test_normalize_job_dispatches_by_source():
    job = {"_source": "adzuna", "title": "X", "company": {"display_name": "Y"}, "location": {}}
    result = normalize_job(job)
    assert result["source"] == "Adzuna"


def test_normalize_job_unknown_source_returns_none():
    assert normalize_job({"_source": "linkedin", "title": "X"}) is None


def test_normalize_job_missing_source_tag_returns_none():
    assert normalize_job({"title": "X"}) is None


def test_normalize_jobs_skips_unrecognized_and_keeps_valid():
    jobs = [
        {"_source": "adzuna", "title": "A", "company": {}, "location": {}},
        {"_source": "unknown_source", "title": "B"},
        {"_source": "arbeitnow", "title": "C"},
    ]
    result = normalize_jobs(jobs)
    assert len(result) == 2
    assert result[0]["title"] == "A"
    assert result[1]["title"] == "C"


def test_normalize_jobs_empty_list():
    assert normalize_jobs([]) == []


def test_remove_duplicate_jobs_by_source_id():
    jobs = [
        {"source": "Adzuna", "source_id": "1", "title": "A", "company": "X", "location": "Y"},
        {"source": "Adzuna", "source_id": "1", "title": "A different title now", "company": "X", "location": "Y2"},
    ]
    result = remove_duplicate_jobs(jobs)
    assert len(result) == 1
    assert result[0]["title"] == "A"


def test_remove_duplicate_jobs_by_content_key_case_insensitive():
    jobs = [
        {"source": "Adzuna", "source_id": "1", "title": "Python Dev", "company": "Acme", "location": "Delhi"},
        {"source": "Jooble", "source_id": "2", "title": "python dev", "company": "ACME", "location": "delhi"},
    ]
    result = remove_duplicate_jobs(jobs)
    assert len(result) == 1


def test_remove_duplicate_jobs_keeps_distinct_jobs():
    jobs = [
        {"source": "Adzuna", "source_id": "1", "title": "Python Dev", "company": "Acme", "location": "Delhi"},
        {"source": "Jooble", "source_id": "2", "title": "Java Dev", "company": "Beta", "location": "Mumbai"},
    ]
    result = remove_duplicate_jobs(jobs)
    assert len(result) == 2


def test_remove_duplicate_jobs_missing_source_id_not_falsely_matched():
    # Jobs without a source_id should never dedupe against each other via the id check,
    # only via content key, since empty string source_ids would otherwise collide.
    jobs = [
        {"source": "Arbeitnow", "source_id": "", "title": "A", "company": "X", "location": "Y"},
        {"source": "Arbeitnow", "source_id": "", "title": "B", "company": "X", "location": "Y"},
    ]
    result = remove_duplicate_jobs(jobs)
    assert len(result) == 2


def test_remove_duplicate_jobs_empty_list():
    assert remove_duplicate_jobs([]) == []


def _job(source, n):
    return {"source": source, "title": f"{source} job {n}"}


def test_select_balanced_jobs_round_robins_across_sources():
    jobs = (
        [_job("Adzuna", i) for i in range(10)]
        + [_job("Jooble", i) for i in range(10)]
        + [_job("Arbeitnow", i) for i in range(10)]
    )
    result = select_balanced_jobs(jobs, limit=6)
    sources = [job["source"] for job in result]
    assert sources == ["Adzuna", "Jooble", "Arbeitnow", "Adzuna", "Jooble", "Arbeitnow"]


def test_select_balanced_jobs_one_source_cannot_crowd_out_others():
    # Adzuna alone has more than the limit; Jooble/Arbeitnow have just one each.
    # A plain positional slice would return only Adzuna jobs - this must not.
    jobs = [_job("Adzuna", i) for i in range(20)] + [_job("Jooble", 0)] + [_job("Arbeitnow", 0)]
    result = select_balanced_jobs(jobs, limit=5)
    sources = {job["source"] for job in result}
    assert sources == {"Adzuna", "Jooble", "Arbeitnow"}


def test_select_balanced_jobs_respects_limit():
    jobs = [_job("Adzuna", i) for i in range(50)]
    result = select_balanced_jobs(jobs, limit=15)
    assert len(result) == 15


def test_select_balanced_jobs_fewer_jobs_than_limit_returns_all():
    jobs = [_job("Adzuna", 0), _job("Jooble", 0)]
    result = select_balanced_jobs(jobs, limit=15)
    assert len(result) == 2


def test_select_balanced_jobs_empty_list():
    assert select_balanced_jobs([], limit=15) == []


def test_select_balanced_jobs_missing_source_field_still_works():
    jobs = [{"title": "no source"} for _ in range(3)]
    result = select_balanced_jobs(jobs, limit=2)
    assert len(result) == 2


def test_normalize_job_passes_through_already_normalized_job():
    from app.services.job_normalizer import normalize_job
    job = {"title": "Python Developer", "source": "Adzuna", "source_id": "1"}
    assert normalize_job(job) is job
