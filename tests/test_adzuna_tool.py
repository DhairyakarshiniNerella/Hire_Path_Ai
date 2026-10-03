import requests
from app.tools import adzuna_tool


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def test_missing_credentials_returns_error(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", None)
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", None)
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "credentials" in result["error"].lower()


def test_successful_search_returns_jobs(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")

    def fake_get(url, params=None, timeout=None):
        return FakeResponse(200, {"results": [{"title": "Python Dev"}]})

    monkeypatch.setattr(adzuna_tool.requests, "get", fake_get)
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is True
    assert result["jobs"] == [{"title": "Python Dev"}]


def test_successful_search_with_no_results_key(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(adzuna_tool.requests, "get", lambda *a, **k: FakeResponse(200, {}))
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is True
    assert result["jobs"] == []


def test_unauthorized_credentials(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(adzuna_tool.requests, "get", lambda *a, **k: FakeResponse(401))
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "credentials" in result["error"].lower()


def test_rate_limit_response(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(adzuna_tool.requests, "get", lambda *a, **k: FakeResponse(429))
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "rate limit" in result["error"].lower()


def test_other_error_status_code(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    monkeypatch.setattr(adzuna_tool.requests, "get", lambda *a, **k: FakeResponse(500))
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "500" in result["error"]


def test_timeout_returns_error(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")

    def fake_get(*a, **k):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(adzuna_tool.requests, "get", fake_get)
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "timed out" in result["error"].lower()


def test_network_error_returns_error(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")

    def fake_get(*a, **k):
        raise requests.exceptions.ConnectionError("boom")

    monkeypatch.setattr(adzuna_tool.requests, "get", fake_get)
    result = adzuna_tool.search_adzuna_jobs("Python Developer")
    assert result["success"] is False
    assert "network error" in result["error"].lower()


def test_location_param_included_when_given(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    captured_params = {}

    def fake_get(url, params=None, timeout=None):
        captured_params.update(params)
        return FakeResponse(200, {"results": []})

    monkeypatch.setattr(adzuna_tool.requests, "get", fake_get)
    adzuna_tool.search_adzuna_jobs("Python Developer", location="Mumbai")
    assert captured_params["where"] == "Mumbai"


def test_location_param_omitted_when_blank(monkeypatch):
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_ID", "id")
    monkeypatch.setattr(adzuna_tool, "ADZUNA_APP_KEY", "key")
    captured_params = {}

    def fake_get(url, params=None, timeout=None):
        captured_params.update(params)
        return FakeResponse(200, {"results": []})

    monkeypatch.setattr(adzuna_tool.requests, "get", fake_get)
    adzuna_tool.search_adzuna_jobs("Python Developer")
    assert "where" not in captured_params
