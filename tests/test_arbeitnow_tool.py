import requests
from app.tools import arbeitnow_tool


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


SAMPLE_JOBS = [
    {"title": "Python Backend Developer", "tags": ["python", "backend"]},
    {"title": "Frontend Engineer", "tags": ["react", "javascript"]},
    {"title": "DevOps Specialist", "tags": ["python", "docker"]},
]


def test_successful_fetch_no_query_returns_all_jobs(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": SAMPLE_JOBS}))
    result = arbeitnow_tool.search_arbeitnow_jobs()
    assert result["success"] is True
    assert len(result["jobs"]) == 3


def test_query_filters_by_title_case_insensitive(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": SAMPLE_JOBS}))
    result = arbeitnow_tool.search_arbeitnow_jobs("python")
    titles = [job["title"] for job in result["jobs"]]
    assert "Python Backend Developer" in titles
    assert "DevOps Specialist" in titles  # matched via tag, not title
    assert "Frontend Engineer" not in titles


def test_query_filters_by_tag(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": SAMPLE_JOBS}))
    result = arbeitnow_tool.search_arbeitnow_jobs("react")
    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["title"] == "Frontend Engineer"


def test_query_no_matches_returns_empty_list(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": SAMPLE_JOBS}))
    result = arbeitnow_tool.search_arbeitnow_jobs("rust")
    assert result["success"] is True
    assert result["jobs"] == []


def test_rate_limit_response(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(429))
    result = arbeitnow_tool.search_arbeitnow_jobs("python")
    assert result["success"] is False
    assert "rate limit" in result["error"].lower()


def test_other_error_status(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(500))
    result = arbeitnow_tool.search_arbeitnow_jobs()
    assert result["success"] is False
    assert "500" in result["error"]


def test_timeout(monkeypatch):
    def fake_get(*a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(arbeitnow_tool.requests, "get", fake_get)
    result = arbeitnow_tool.search_arbeitnow_jobs()
    assert result["success"] is False
    assert "timed out" in result["error"].lower()


def test_network_error(monkeypatch):
    def fake_get(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(arbeitnow_tool.requests, "get", fake_get)
    result = arbeitnow_tool.search_arbeitnow_jobs()
    assert result["success"] is False
    assert "network error" in result["error"].lower()


def test_missing_data_key_defaults_to_empty_list(monkeypatch):
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {}))
    result = arbeitnow_tool.search_arbeitnow_jobs()
    assert result["jobs"] == []


def test_multi_word_query_matches_on_individual_words(monkeypatch):
    # A real posting rarely contains the whole generated phrase verbatim -
    # "Machine Learning Engineer" should still match "Senior ML Engineer"
    # because "engineer" is a shared word, even though the full phrase isn't a substring.
    jobs = [{"title": "Senior ML Engineer", "tags": []}, {"title": "Sales Associate", "tags": []}]
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": jobs}))
    result = arbeitnow_tool.search_arbeitnow_jobs("Machine Learning Engineer")
    titles = [job["title"] for job in result["jobs"]]
    assert "Senior ML Engineer" in titles
    assert "Sales Associate" not in titles


def test_query_short_words_only_returns_all_jobs_unfiltered(monkeypatch):
    # Every word is <=2 chars, so there's nothing meaningful to filter on -
    # falls back to returning the full unfiltered list instead of an empty one.
    monkeypatch.setattr(arbeitnow_tool.requests, "get", lambda *a, **k: FakeResponse(200, {"data": SAMPLE_JOBS}))
    result = arbeitnow_tool.search_arbeitnow_jobs("go")
    assert len(result["jobs"]) == 3


def test_job_with_no_tags_field_does_not_crash_on_query(monkeypatch):
    monkeypatch.setattr(
        arbeitnow_tool.requests, "get",
        lambda *a, **k: FakeResponse(200, {"data": [{"title": "No Tags Job"}]}),
    )
    result = arbeitnow_tool.search_arbeitnow_jobs("python")
    assert result["success"] is True
    assert result["jobs"] == []
