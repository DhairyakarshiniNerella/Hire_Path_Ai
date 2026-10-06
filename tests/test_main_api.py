import io
import pytest
from app import main as main_module


# Long enough to clear the minimum-words check that guards the LLM call
REALISTIC_TEXT = "Jane Doe Software Engineer " + "built backend services in Python and SQL " * 5


@pytest.fixture
def client():
    main_module.app.config["TESTING"] = True
    return main_module.app.test_client()


def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "message": "HirePath AI backend is running"}


def test_upload_missing_file_part(client):
    response = client.post("/api/resume/upload", data={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "No file was sent"


def test_upload_empty_filename(client):
    data = {"resume": (io.BytesIO(b"content"), "")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "No file was selected"


def test_upload_disallowed_file_type(client):
    data = {"resume": (io.BytesIO(b"content"), "resume.exe")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "Only PDF and DOCX files are allowed"


def test_upload_extraction_failure_returns_400(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": False, "error": "Could not read file: boom"},
    )
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert response.get_json()["error"] == "Could not read file: boom"


def test_upload_workflow_exception_returns_500(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )

    def boom(initial_state, config=None):
        raise RuntimeError("graph exploded")

    monkeypatch.setattr(main_module.workflow, "invoke", boom)
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 500
    assert "Workflow failed unexpectedly" in response.get_json()["error"]


def test_upload_workflow_reports_agent_errors_returns_502(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )
    monkeypatch.setattr(
        main_module.workflow, "invoke",
        lambda state, config=None: {"errors": ["Resume Analyzer Agent failed: bad output"]},
    )
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 502
    assert "Resume Analyzer Agent failed" in response.get_json()["error"]


def test_upload_workflow_missing_profile_returns_500(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )
    monkeypatch.setattr(
        main_module.workflow, "invoke",
        lambda state, config=None: {"errors": [], "candidate_profile": None},
    )
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 500
    assert response.get_json()["error"] == "Could not analyze the resume"


def test_upload_success_returns_full_payload(client, monkeypatch):
    from app.models.profile import CandidateProfile

    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )
    fake_profile = CandidateProfile(name="Jane Doe", skills=["Python"])
    monkeypatch.setattr(
        main_module.workflow, "invoke",
        lambda state, config=None: {
            "errors": [],
            "candidate_profile": fake_profile,
            "search_queries": ["Python Developer"],
            "recommendations": [{"title": "Backend Dev", "match_score": 90}],
        },
    )
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    body = response.get_json()

    assert response.status_code == 200
    assert body["status"] == "ok"
    assert body["candidate_profile"]["name"] == "Jane Doe"
    assert body["search_queries"] == ["Python Developer"]
    assert body["recommendations"] == [{"title": "Backend Dev", "match_score": 90}]
    assert "token_usage" in body


def test_is_allowed_file_accepts_pdf_and_docx():
    assert main_module.is_allowed_file("resume.pdf") is True
    assert main_module.is_allowed_file("resume.docx") is True
    assert main_module.is_allowed_file("resume.PDF") is True


def test_is_allowed_file_rejects_other_extensions():
    assert main_module.is_allowed_file("resume.exe") is False
    assert main_module.is_allowed_file("resume.txt") is False


def test_is_allowed_file_rejects_no_extension():
    assert main_module.is_allowed_file("resume") is False


@pytest.mark.parametrize("text", ["hello", "resume text", "word " * 19])
def test_upload_rejects_too_little_text_without_calling_the_llm(client, monkeypatch, text):
    monkeypatch.setattr(main_module, "extract_resume_text", lambda path: {"success": True, "text": text})

    def must_not_run(initial_state, config=None):
        raise AssertionError("LLM workflow should not run for near-empty text")

    monkeypatch.setattr(main_module.workflow, "invoke", must_not_run)
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/upload", data=data, content_type="multipart/form-data")
    assert response.status_code == 400
    assert "very little readable text" in response.get_json()["error"]


# ---------- start-and-poll flow ----------

def _wait_for_job(client, job_id, attempts=100):
    import time
    for _ in range(attempts):
        body = client.get(f"/api/resume/status/{job_id}").get_json()
        if body.get("status") != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("job never finished")


def test_start_validation_errors_match_upload(client):
    response = client.post("/api/resume/start", data={})
    assert response.status_code == 400
    assert response.get_json()["error"] == "No file was sent"


def test_start_then_status_returns_result(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )
    monkeypatch.setattr(
        main_module, "_analyze_resume_text",
        lambda text: ({"status": "ok", "recommendations": []}, 200),
    )
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    response = client.post("/api/resume/start", data=data, content_type="multipart/form-data")
    assert response.status_code == 202

    body = _wait_for_job(client, response.get_json()["job_id"])
    assert body == {"status": "done", "http_status": 200, "result": {"status": "ok", "recommendations": []}}


def test_status_reports_pipeline_errors_with_their_http_status(client, monkeypatch):
    monkeypatch.setattr(
        main_module, "extract_resume_text",
        lambda path: {"success": True, "text": REALISTIC_TEXT},
    )
    monkeypatch.setattr(main_module, "_analyze_resume_text", lambda text: ({"error": "agent failed"}, 502))
    data = {"resume": (io.BytesIO(b"content"), "resume.pdf")}
    job_id = client.post("/api/resume/start", data=data, content_type="multipart/form-data").get_json()["job_id"]

    body = _wait_for_job(client, job_id)
    assert body["http_status"] == 502
    assert body["result"]["error"] == "agent failed"


def test_status_unknown_job_returns_404(client):
    response = client.get("/api/resume/status/does-not-exist")
    assert response.status_code == 404


# ---------- diagnostics + request tagging ----------

def test_diagnostics_is_hidden_without_a_configured_token(client, monkeypatch):
    monkeypatch.delenv("DIAGNOSTICS_TOKEN", raising=False)
    assert client.get("/api/diagnostics").status_code == 404
    assert client.get("/api/diagnostics", headers={"X-Diagnostics-Token": ""}).status_code == 404


def test_diagnostics_rejects_a_wrong_token_and_returns_no_secrets(client, monkeypatch):
    monkeypatch.setenv("DIAGNOSTICS_TOKEN", "diag-token")
    monkeypatch.setenv("MCP_AUTH_TOKEN", "mcp-secret-value")
    monkeypatch.setattr(main_module, "check_mcp_connection", lambda deep=False: {"auth_and_handshake_ok": True})

    assert client.get("/api/diagnostics", headers={"X-Diagnostics-Token": "nope"}).status_code == 404

    response = client.get("/api/diagnostics", headers={"X-Diagnostics-Token": "diag-token"})
    assert response.status_code == 200
    assert response.get_json()["mcp"] == {"auth_and_handshake_ok": True}
    assert "mcp-secret-value" not in response.get_data(as_text=True)


def test_api_responses_are_never_cached_and_carry_a_request_id(client):
    response = client.get("/api/health")
    assert response.headers["Cache-Control"] == "no-store"
    assert len(response.headers["X-Request-ID"]) == 8
