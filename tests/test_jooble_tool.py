import requests
from app.tools import jooble_tool


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def test_missing_api_key_returns_error(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", None)
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "key is missing" in result["error"].lower()


def test_successful_search_returns_jobs(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(jooble_tool.requests, "post", lambda *a, **k: FakeResponse(200, {"jobs": [{"title": "Dev"}]}))
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is True
    assert result["jobs"] == [{"title": "Dev"}]


def test_unauthorized_key(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(jooble_tool.requests, "post", lambda *a, **k: FakeResponse(401))
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "rejected" in result["error"].lower()


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(jooble_tool.requests, "post", lambda *a, **k: FakeResponse(429))
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "rate limit" in result["error"].lower()


def test_other_error_status(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(jooble_tool.requests, "post", lambda *a, **k: FakeResponse(503))
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "503" in result["error"]


def test_timeout(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")

    def fake_post(*a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(jooble_tool.requests, "post", fake_post)
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "timed out" in result["error"].lower()


def test_network_error(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")

    def fake_post(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(jooble_tool.requests, "post", fake_post)
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["success"] is False
    assert "network error" in result["error"].lower()


def test_payload_includes_keywords_and_location(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured.update(json)
        return FakeResponse(200, {"jobs": []})

    monkeypatch.setattr(jooble_tool.requests, "post", fake_post)
    jooble_tool.search_jooble_jobs("Data Scientist", location="Pune")
    assert captured == {"keywords": "Data Scientist", "location": "Pune"}


def test_missing_jobs_key_defaults_to_empty_list(monkeypatch):
    monkeypatch.setattr(jooble_tool, "JOOBLE_API_KEY", "key")
    monkeypatch.setattr(jooble_tool.requests, "post", lambda *a, **k: FakeResponse(200, {}))
    result = jooble_tool.search_jooble_jobs("Python Developer")
    assert result["jobs"] == []
