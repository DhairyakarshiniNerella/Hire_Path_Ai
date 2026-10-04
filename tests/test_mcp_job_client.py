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
