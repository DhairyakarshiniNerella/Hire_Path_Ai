import pytest

from app.services import mcp_job_client


def test_server_env_passes_only_the_job_source_credentials(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "fake-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "fake-key")
    monkeypatch.setenv("JOOBLE_API_KEY", "fake-jooble")
    monkeypatch.setenv("GROQ_API_KEY", "must-not-be-forwarded")

    assert mcp_job_client._server_env() == {
        "ADZUNA_APP_ID": "fake-id",
        "ADZUNA_APP_KEY": "fake-key",
        "JOOBLE_API_KEY": "fake-jooble",
    }


def test_server_env_skips_missing_or_empty_variables(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "fake-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "")
    monkeypatch.delenv("JOOBLE_API_KEY", raising=False)

    assert mcp_job_client._server_env() == {"ADZUNA_APP_ID": "fake-id"}


def test_server_params_include_the_env_and_start_the_server_module(monkeypatch):
    monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
    monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
    monkeypatch.setenv("JOOBLE_API_KEY", "fake-jooble")

    params = mcp_job_client._server_params()

    assert params.args == ["-m", "mcp_server.server"]
    assert params.env == {"JOOBLE_API_KEY": "fake-jooble"}


# ---------- remote (HTTP) mode ----------

def test_remote_server_is_none_when_url_not_set(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    assert mcp_job_client._remote_server() is None


def test_remote_server_builds_endpoint_and_bearer_header(monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "secret-token")
    for base in ("https://x.onrender.com", "https://x.onrender.com/", "https://x.onrender.com/mcp"):
        monkeypatch.setenv("MCP_SERVER_URL", base)
        url, headers = mcp_job_client._remote_server()
        assert url == "https://x.onrender.com/mcp"
        assert headers == {"Authorization": "Bearer secret-token"}


def test_remote_server_requires_a_token(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "https://x.onrender.com")
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)

    with pytest.raises(RuntimeError) as err:
        mcp_job_client._remote_server()

    assert "MCP_AUTH_TOKEN" in str(err.value)


def test_remote_error_message_never_contains_the_token(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "https://x.onrender.com")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "")
    with pytest.raises(RuntimeError) as err:
        mcp_job_client._remote_server()
    assert "Bearer" not in str(err.value)


def test_root_cause_unwraps_nested_exception_groups():
    inner = ExceptionGroup("inner", [ValueError("401 Unauthorized")])
    outer = ExceptionGroup("unhandled errors in a TaskGroup", [inner])

    assert mcp_job_client._root_cause(outer) == "ValueError: 401 Unauthorized"


def test_batch_search_reports_the_root_cause_not_the_taskgroup_message(monkeypatch):
    async def boom(queries, location, limit):
        raise ExceptionGroup("unhandled errors in a TaskGroup", [ConnectionError("server unreachable")])

    monkeypatch.setattr(mcp_job_client, "_call_search_jobs", boom)

    with pytest.raises(RuntimeError, match="ConnectionError: server unreachable"):
        mcp_job_client.search_jobs_batch_via_mcp(["x"])


# ---------- waking a sleeping remote server ----------

class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


def test_wake_does_nothing_when_remote_mode_is_off(monkeypatch):
    monkeypatch.delenv("MCP_SERVER_URL", raising=False)
    monkeypatch.setattr(mcp_job_client.requests, "get", lambda *a, **k: pytest.fail("must not call the network"))
    assert mcp_job_client.wake_remote_server() is False


def test_wake_waits_through_502s_until_the_server_is_up(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "https://x.onrender.com/mcp")
    monkeypatch.setattr(mcp_job_client.time, "sleep", lambda s: None)
    statuses = iter([502, 502, 200])
    urls = []

    def fake_get(url, timeout):
        urls.append(url)
        return _FakeResponse(next(statuses))

    monkeypatch.setattr(mcp_job_client.requests, "get", fake_get)

    assert mcp_job_client.wake_remote_server() is True
    assert urls == ["https://x.onrender.com/health"] * 3


def test_wake_survives_connection_errors_then_gives_up_on_timeout(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "https://x.onrender.com")
    monkeypatch.setattr(mcp_job_client.time, "sleep", lambda s: None)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(mcp_job_client.time, "monotonic", lambda: next(clock))

    def refuse(url, timeout):
        raise mcp_job_client.requests.ConnectionError("down")

    monkeypatch.setattr(mcp_job_client.requests, "get", refuse)

    assert mcp_job_client.wake_remote_server(timeout=30) is False


def test_batch_search_wakes_the_server_before_searching(monkeypatch):
    order = []
    monkeypatch.setattr(mcp_job_client, "wake_remote_server", lambda: order.append("wake"))

    async def fake_call(queries, location, limit):
        order.append("search")
        return []

    monkeypatch.setattr(mcp_job_client, "_call_search_jobs", fake_call)
    mcp_job_client.search_jobs_batch_via_mcp(["x"])
    assert order == ["wake", "search"]
