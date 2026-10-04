import os
import threading
import time
import uuid
from flask import Flask, request
from flask_cors import CORS
from app.tools.resume_parser import extract_resume_text
from app.graph.workflow import workflow
from app.services.token_tracker import reset_usage, get_usage_summary

# Create the Flask application
app = Flask(__name__)

# Allow the browser frontend to call this backend
CORS(app)

# Folder where uploaded resumes will be temporarily saved
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Only these file extensions are allowed
ALLOWED_EXTENSIONS = {"pdf", "docx"}

# Resumes with fewer words than this are rejected before any LLM call
MIN_RESUME_WORDS = 20


def is_allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/api/health")
def health():
    return {"status": "ok", "message": "HirePath AI backend is running"}


def _read_resume_upload():
    """
    Validates the uploaded file and extracts its text.
    Returns (text, None) on success or (None, (error_body, http_status)) on failure.
    """
    if "resume" not in request.files:
        return None, ({"error": "No file was sent"}, 400)

    file = request.files["resume"]

    if file.filename == "":
        return None, ({"error": "No file was selected"}, 400)

    if not is_allowed_file(file.filename):
        return None, ({"error": "Only PDF and DOCX files are allowed"}, 400)

    save_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(save_path)

    extraction_result = extract_resume_text(save_path)
    if not extraction_result["success"]:
        return None, ({"error": extraction_result["error"]}, 400)

    # A real resume has far more than a few words; failing here is instant, whereas
    # sending near-empty text to the LLM wastes retries and ends in a vague error.
    if len(extraction_result["text"].split()) < MIN_RESUME_WORDS:
        return None, ({"error": "This file has very little readable text. Please upload a text-based PDF or DOCX of your resume."}, 400)

    return extraction_result["text"], None


def _analyze_resume_text(resume_text):
    """
    Runs the full multi-agent LangGraph workflow on the resume text.
    Returns (response_body, http_status).
    """
    reset_usage()  # start counting tokens fresh for this run

    initial_state = {
        "resume_text": resume_text,
        "candidate_profile": None,
        "search_queries": [],
        "jobs": None,
        "search_via": None,
        "analyzed_jobs": None,
        "ranked_jobs": None,
        "recommendations": None,
        "errors": [],
        "current_agent": "",
    }

    try:
        # recursion_limit caps how many Supervisor loops can run, so any
        # future bug like this fails fast with a clear error instead of
        # hanging or crashing unpredictably
        final_state = workflow.invoke(initial_state, config={"recursion_limit": 20})

    except Exception as e:
        return {"error": f"Workflow failed unexpectedly: {str(e)}"}, 500

    if final_state.get("errors"):
        return {"error": "; ".join(final_state["errors"])}, 502

    candidate_profile = final_state.get("candidate_profile")
    if candidate_profile is None:
        return {"error": "Could not analyze the resume"}, 500

    return {
        "status": "ok",
        "candidate_profile": candidate_profile.model_dump(),
        "search_queries": final_state.get("search_queries", []),
        "search_via": final_state.get("search_via"),
        "recommendations": final_state.get("recommendations", []),
        "token_usage": get_usage_summary(),
    }, 200


@app.route("/api/resume/upload", methods=["POST"])
def upload_resume():
    """
    Full pipeline endpoint: receives a resume file, runs the complete LangGraph
    multi-agent workflow, and returns the candidate profile plus ranked, explained
    job recommendations. One long request - see /api/resume/start for the
    start-and-poll version the frontend uses.
    """
    text, error = _read_resume_upload()
    if error:
        return error
    return _analyze_resume_text(text)


# --- Start-and-poll version of the pipeline ---
# The workflow takes 1-2 minutes. Holding one HTTP request open that long gets cut by
# many networks (idle timeouts on proxies, mobile data, VPNs), which the browser sees as
# a network error. Here /start returns a job id immediately, the workflow runs in a
# background thread, and the browser polls /status with short requests.
# Jobs live in memory: fine for the single-worker deployment, lost if the service restarts.
JOB_TTL_SECONDS = 30 * 60
_jobs = {}
_jobs_lock = threading.Lock()


def _prune_old_jobs():
    cutoff = time.time() - JOB_TTL_SECONDS
    with _jobs_lock:
        for job_id in [j for j, job in _jobs.items() if job["created"] < cutoff]:
            del _jobs[job_id]


def _run_job(job_id, resume_text):
    try:
        body, status_code = _analyze_resume_text(resume_text)
    except Exception as e:  # never leave a job stuck in "running"
        body, status_code = {"error": f"Workflow failed unexpectedly: {str(e)}"}, 500
    with _jobs_lock:
        _jobs[job_id].update(state="done", body=body, status_code=status_code)


@app.route("/api/resume/start", methods=["POST"])
def start_resume_analysis():
    text, error = _read_resume_upload()
    if error:
        return error

    _prune_old_jobs()
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {"state": "running", "created": time.time()}
    threading.Thread(target=_run_job, args=(job_id, text), daemon=True).start()
    return {"job_id": job_id}, 202


@app.route("/api/resume/status/<job_id>")
def resume_analysis_status(job_id):
    with _jobs_lock:
        job = _jobs.get(job_id)
        job = dict(job) if job else None
    if job is None:
        return {"error": "Unknown or expired job. The server may have restarted - please try again."}, 404
    if job["state"] == "running":
        return {"status": "running"}
    return {"status": "done", "http_status": job["status_code"], "result": job["body"]}


if __name__ == "__main__":
    app.run(debug=True, port=5000)
