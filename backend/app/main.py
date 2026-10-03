import os
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


@app.route("/api/resume/upload", methods=["POST"])
def upload_resume():
    """
    Full pipeline endpoint: receives a resume file, extracts its text,
    runs the complete LangGraph multi-agent workflow, and returns the
    candidate profile plus ranked, explained job recommendations.
    """
    # --- Step 1: Validate and save the uploaded file ---
    if "resume" not in request.files:
        return {"error": "No file was sent"}, 400

    file = request.files["resume"]

    if file.filename == "":
        return {"error": "No file was selected"}, 400

    if not is_allowed_file(file.filename):
        return {"error": "Only PDF and DOCX files are allowed"}, 400

    save_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(save_path)

    # --- Step 2: Extract text from the file ---
    extraction_result = extract_resume_text(save_path)
    if not extraction_result["success"]:
        return {"error": extraction_result["error"]}, 400

    # A real resume has far more than a few words; failing here is instant, whereas
    # sending near-empty text to the LLM wastes retries and ends in a vague error.
    if len(extraction_result["text"].split()) < MIN_RESUME_WORDS:
        return {"error": "This file has very little readable text. Please upload a text-based PDF or DOCX of your resume."}, 400

    # --- Step 3: Run the full multi-agent LangGraph workflow ---
    reset_usage()  # start counting tokens fresh for this run

    initial_state = {
        "resume_text": extraction_result["text"],
        "candidate_profile": None,
        "search_queries": [],
        "jobs": None,
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

    # --- Step 4: Handle agent-reported errors gracefully ---
    if final_state.get("errors"):
        return {"error": "; ".join(final_state["errors"])}, 502

    candidate_profile = final_state.get("candidate_profile")
    if candidate_profile is None:
        return {"error": "Could not analyze the resume"}, 500

    # --- Step 5: Return the results as JSON ---
    return {
        "status": "ok",
        "candidate_profile": candidate_profile.model_dump(),
        "search_queries": final_state.get("search_queries", []),
        "recommendations": final_state.get("recommendations", []),
        "token_usage": get_usage_summary(),
    }


if __name__ == "__main__":
    app.run(debug=True, port=5000)
