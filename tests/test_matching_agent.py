from app.agents.matching_agent import rank_jobs_for_candidate
from app.agents import matching_agent


def test_rank_jobs_sorts_best_match_first(monkeypatch):
    scores = {"Job A": 55, "Job B": 90, "Job C": 65}

    def fake_calculate_match_score(candidate_profile, job):
        return {"match_score": scores[job["title"]]}

    monkeypatch.setattr(matching_agent, "calculate_match_score", fake_calculate_match_score)

    jobs = [{"title": "Job A"}, {"title": "Job B"}, {"title": "Job C"}]
    ranked = rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=jobs)

    assert [job["title"] for job in ranked] == ["Job B", "Job C", "Job A"]


def test_rank_jobs_filters_out_jobs_below_threshold(monkeypatch):
    scores = {"Job A": 20, "Job B": 90, "Job C": 39}

    def fake_calculate_match_score(candidate_profile, job):
        return {"match_score": scores[job["title"]]}

    monkeypatch.setattr(matching_agent, "calculate_match_score", fake_calculate_match_score)

    jobs = [{"title": "Job A"}, {"title": "Job B"}, {"title": "Job C"}]
    ranked = rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=jobs)

    assert [job["title"] for job in ranked] == ["Job B"]


def test_rank_jobs_includes_jobs_at_exactly_threshold(monkeypatch):
    monkeypatch.setattr(matching_agent, "calculate_match_score", lambda *a, **k: {"match_score": 40})
    jobs = [{"title": "Job A"}]
    ranked = rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=jobs)
    assert [job["title"] for job in ranked] == ["Job A"]


def test_rank_jobs_merges_score_fields_into_job_dict(monkeypatch):
    def fake_calculate_match_score(candidate_profile, job):
        return {"match_score": 75, "matched_skills": ["Python"]}

    monkeypatch.setattr(matching_agent, "calculate_match_score", fake_calculate_match_score)

    jobs = [{"title": "Job A", "company": "Acme"}]
    ranked = rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=jobs)

    assert ranked[0]["company"] == "Acme"  # original fields preserved
    assert ranked[0]["match_score"] == 75
    assert ranked[0]["matched_skills"] == ["Python"]


def test_rank_jobs_empty_list_returns_empty_list(monkeypatch):
    monkeypatch.setattr(matching_agent, "calculate_match_score", lambda *a, **k: {"match_score": 0})
    assert rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=[]) == []


def test_rank_jobs_stable_for_equal_scores(monkeypatch):
    monkeypatch.setattr(matching_agent, "calculate_match_score", lambda *a, **k: {"match_score": 40})
    jobs = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
    ranked = rank_jobs_for_candidate(candidate_profile=None, analyzed_jobs=jobs)
    # Python's sort is stable, so equal scores keep their original relative order
    assert [job["title"] for job in ranked] == ["A", "B", "C"]


def test_rank_jobs_drops_jobs_whose_posting_lists_skills_but_none_match(monkeypatch):
    results = {
        "No overlap": {"match_score": 45, "skills_listed": True, "matched_skills": []},
        "Some overlap": {"match_score": 45, "skills_listed": True, "matched_skills": ["Python"]},
        "Snippet only": {"match_score": 45, "skills_listed": False, "matched_skills": []},
    }
    monkeypatch.setattr(matching_agent, "calculate_match_score", lambda profile, job: results[job["title"]])

    ranked = rank_jobs_for_candidate(None, [{"title": t} for t in results])

    assert [job["title"] for job in ranked] == ["Some overlap", "Snippet only"]
