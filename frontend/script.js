// --- Dark mode toggle ---
const themeToggleButton = document.getElementById("theme-toggle");

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    themeToggleButton.textContent = theme === "dark" ? "☀️" : "🌙";
}

(function initTheme() {
    let savedTheme = "light";
    try {
        savedTheme = localStorage.getItem("hirepath-theme") || "light";
    } catch (error) {
        // localStorage can be unavailable (private browsing, etc.) - just default to light
    }
    applyTheme(savedTheme);
})();

themeToggleButton.addEventListener("click", () => {
    const isDark = document.documentElement.getAttribute("data-theme") === "dark";
    const newTheme = isDark ? "light" : "dark";
    applyTheme(newTheme);
    try {
        localStorage.setItem("hirepath-theme", newTheme);
    } catch (error) {
        // Ignore - just means the preference won't persist across reloads
    }
});

// --- Backend API base URL ---
// Locally (Vercel dev, or opening index.html directly) this points at your
// local Flask server. In production, replace the placeholder below with
// your deployed backend's URL (e.g. from Render/Railway/Fly.io).
const API_BASE_URL = ["localhost", "127.0.0.1"].includes(window.location.hostname)
    ? "http://127.0.0.1:5000"
    : "https://hirepath-ai-backend.onrender.com";

// --- Backend status pill (auto-checked on page load) ---
const backendStatusDot = document.getElementById("backend-status-dot");
const backendStatusText = document.getElementById("backend-status-text");

async function checkBackendStatus() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/health`);
        if (!response.ok) throw new Error("Backend responded with an error");
        backendStatusDot.className = "status-dot status-online";
        backendStatusText.textContent = "Backend online";
    } catch (error) {
        backendStatusDot.className = "status-dot status-offline";
        backendStatusText.textContent = "Backend offline";
    }
}

checkBackendStatus();

// --- Resume upload + full workflow ---

const resumeInput = document.getElementById("resume-input");
const dropzone = document.getElementById("dropzone");
const fileDropLabel = document.getElementById("file-drop-label");
const analyzeButton = document.getElementById("analyze-btn");
const statusMessage = document.getElementById("status-message");
const profileSection = document.getElementById("profile-section");
const recommendationsSection = document.getElementById("recommendations-section");

function showSelectedFileName() {
    const file = resumeInput.files[0];
    fileDropLabel.textContent = file
        ? `Selected: ${file.name}`
        : "Drag & drop your resume, or browse";
}

// Clicking anywhere on the dropzone opens the native file picker
dropzone.addEventListener("click", () => resumeInput.click());
resumeInput.addEventListener("change", showSelectedFileName);

// Drag-and-drop support
["dragover", "dragenter"].forEach((eventName) => {
    dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("dropzone-active");
    });
});

["dragleave", "dragend"].forEach((eventName) => {
    dropzone.addEventListener(eventName, () => {
        dropzone.classList.remove("dropzone-active");
    });
});

dropzone.addEventListener("drop", (event) => {
    event.preventDefault();
    dropzone.classList.remove("dropzone-active");

    if (event.dataTransfer.files.length > 0) {
        resumeInput.files = event.dataTransfer.files;
        showSelectedFileName();
    }
});

// --- Agent progress checklist ---
// NOTE: this is a SIMULATED progression, not a live feed from the backend.
// Our Flask endpoint is one synchronous request, so we don't get real-time
// per-agent updates. This reveals items on a timer while the real request
// is in flight, then snaps everything to "done" the instant the response
// actually arrives. A production version could use Server-Sent Events or
// WebSockets for genuinely live per-agent progress.
const AGENTS = [
    { id: "resume_analyzer", icon: "📄", label: "Resume Analyzer Agent" },
    { id: "job_search", icon: "🔍", label: "Job Search Agent" },
    { id: "job_sources", icon: "🌐", label: "Fetching jobs through the MCP server (Adzuna, Jooble, Arbeitnow)" },
    { id: "job_analysis", icon: "🔎", label: "Job Analysis Agent" },
    { id: "matching", icon: "🎯", label: "Matching Agent" },
    { id: "recommendation", icon: "✨", label: "Recommendation Agent" },
];

const agentProgressSection = document.getElementById("agent-progress");
const agentProgressList = document.getElementById("agent-progress-list");
const progressBarFill = document.getElementById("progress-bar-fill");
let progressIntervalId = null;
let doneCount = 0;

function updateProgressBar() {
    const percent = Math.round((doneCount / AGENTS.length) * 100);
    progressBarFill.style.width = `${percent}%`;
}

function renderAgentChecklist() {
    agentProgressList.innerHTML = "";
    doneCount = 0;
    updateProgressBar();

    AGENTS.forEach((agent) => {
        const li = document.createElement("li");
        li.id = `agent-item-${agent.id}`;
        li.className = "agent-pending";
        li.innerHTML = `<span class="agent-status">○</span> <span class="agent-icon">${agent.icon}</span> ${agent.label}`;
        agentProgressList.appendChild(li);
    });
}

function markAgentDone(agentId) {
    const li = document.getElementById(`agent-item-${agentId}`);
    if (li && li.className !== "agent-done") {
        const agent = AGENTS.find((a) => a.id === agentId);
        li.className = "agent-done";
        li.innerHTML = `<span class="agent-status">✓</span> <span class="agent-icon">${agent.icon}</span> ${agent.label}`;
        doneCount++;
        updateProgressBar();
    }
}

function startSimulatedProgress() {
    renderAgentChecklist();
    agentProgressSection.classList.remove("hidden");
    agentProgressSection.scrollIntoView({ behavior: "smooth", block: "start" });

    let index = 0;
    progressIntervalId = setInterval(() => {
        if (index < AGENTS.length) {
            markAgentDone(AGENTS[index].id);
            index++;
        } else {
            clearInterval(progressIntervalId);
        }
    }, 8000); // reveal roughly one agent every 8 seconds
}

function finishProgress() {
    if (progressIntervalId) clearInterval(progressIntervalId);
    AGENTS.forEach((agent) => markAgentDone(agent.id));
}

// Renders a list of strings as small pill/chip elements inside a container.
function renderChips(container, items, chipClass, emptyText = "Not specified") {
    container.innerHTML = "";
    container.classList.add("chip-row");

    if (!items || items.length === 0) {
        container.classList.remove("chip-row");
        container.textContent = emptyText;
        return;
    }

    items.forEach((item) => {
        const chip = document.createElement("span");
        chip.className = `chip ${chipClass}`;
        chip.textContent = item;
        container.appendChild(chip);
    });
}

// Renders each project with its name highlighted (bold) and description
// as regular text below it - instead of one long comma-joined blob.
function renderProjects(container, projects) {
    container.innerHTML = "";

    if (!projects || projects.length === 0) {
        container.textContent = "Not specified";
        return;
    }

    container.classList.add("project-list");
    projects.forEach((project) => {
        const item = document.createElement("div");
        item.className = "project-item";

        const nameEl = document.createElement("span");
        nameEl.className = "project-name";
        nameEl.textContent = project.name;
        item.appendChild(nameEl);

        if (project.description) {
            const descEl = document.createElement("span");
            descEl.className = "project-desc";
            descEl.textContent = project.description;
            item.appendChild(descEl);
        }

        container.appendChild(item);
    });
}

function displayProfile(profile) {
    document.getElementById("profile-name").textContent = profile.name || "Unknown";
    document.getElementById("profile-career-level").textContent = profile.career_level || "Unknown";
    document.getElementById("profile-education").textContent = profile.education.join(", ") || "Not specified";
    renderChips(document.getElementById("profile-skills"), profile.skills, "chip-neutral");
    document.getElementById("profile-experience").textContent = `${profile.total_experience_years} year(s)`;
    renderProjects(document.getElementById("profile-projects"), profile.projects);
    document.getElementById("profile-target-roles").textContent = profile.target_roles.join(", ") || "Not specified";

    profileSection.classList.remove("hidden");
}

// Tells the user how the jobs were actually fetched (reported by the backend, not assumed).
const MCP_FALLBACK_REASONS = {
    auth: "the MCP server rejected the access token",
    server_waking_or_unavailable: "the MCP server was still waking up",
    timeout: "the MCP server timed out",
    unreachable: "the MCP server could not be reached",
    not_configured: "the MCP connection is not configured",
    bad_request: "the MCP server rejected the request",
};

// The checklist is revealed on a timer, so its job-source line is corrected once the backend has
// said how the jobs were really fetched: a green check must never claim MCP when it fell back.
function updateJobSourcesStep(searchVia, reason) {
    const li = document.getElementById("agent-item-job_sources");
    if (!li || searchVia !== "direct") return;
    const detail = MCP_FALLBACK_REASONS[reason];
    li.className = "agent-pending";
    li.innerHTML = `<span class="agent-status">⚠</span> <span class="agent-icon">🌐</span> `
        + `Jobs fetched directly from Adzuna, Jooble, Arbeitnow (MCP unavailable${detail ? `: ${detail}` : ""})`;
}

function displaySearchVia(searchVia, reason) {
    const note = document.getElementById("search-via-note");
    if (!note) return;
    if (searchVia === "mcp") {
        note.textContent = "🔌 Jobs were fetched through the HirePath MCP server (Model Context Protocol).";
    } else if (searchVia === "direct") {
        const detail = MCP_FALLBACK_REASONS[reason];
        note.textContent = detail
            ? `Jobs were fetched directly from the job APIs (the MCP server was unavailable: ${detail}).`
            : "Jobs were fetched directly from the job APIs (the MCP server was unavailable).";
    } else {
        note.classList.add("hidden");
        return;
    }
    note.classList.remove("hidden");
}

function createEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
}

// The analysis takes 1-2 minutes. One request held open that long gets cut by many networks,
// so the backend returns a job id right away and we check on it with short requests.
// Phones are the hard case: a sleeping free-tier backend answers with an HTML 502 page while
// it wakes (30-60s), and mobile browsers drop requests when the tab is backgrounded or the
// network switches. So both calls are retried instead of failing on the first hiccup.
const POLL_INTERVAL_MS = 3000;
const POLL_MAX_MS = 10 * 60 * 1000;
const RETRY_INTERVAL_MS = 5000;
const START_RETRY_MS = 90 * 1000;          // how long to keep trying to start (backend waking up)
const POLL_MAX_FAILURE_MS = 90 * 1000;     // how long polls may fail in a row before giving up
const RETRYABLE_STATUSES = [502, 503, 504];

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

// fetch + parse JSON. Throws on a network error or a non-JSON reply (e.g. a gateway's HTML error page).
async function fetchJson(url, options) {
    const response = await fetch(url, options);
    const body = await response.json();
    return { response, body };
}

async function startAnalysis(formData) {
    const retryDeadline = Date.now() + START_RETRY_MS;
    while (true) {
        try {
            const { response, body } = await fetchJson(`${API_BASE_URL}/api/resume/start`, {
                method: "POST",
                body: formData,
            });
            if (!RETRYABLE_STATUSES.includes(response.status)) return { response, body };
        } catch (error) {
            if (Date.now() >= retryDeadline) throw error;
        }
        if (Date.now() >= retryDeadline) {
            throw new Error("The backend did not wake up in time");
        }
        await sleep(RETRY_INTERVAL_MS);
    }
}

// Resolves to { ok, data }. Throws only if the backend can't be reached at all.
async function analyzeResume(formData) {
    const { response: startResponse, body: startData } = await startAnalysis(formData);
    if (!startResponse.ok) return { ok: false, data: startData };

    const deadline = Date.now() + POLL_MAX_MS;
    let firstFailureAt = null;
    while (Date.now() < deadline) {
        await sleep(POLL_INTERVAL_MS);
        let response, body;
        try {
            ({ response, body } = await fetchJson(`${API_BASE_URL}/api/resume/status/${startData.job_id}`));
        } catch (error) {
            // A dropped poll is harmless; give up only if the backend stays unreachable for a while.
            if (firstFailureAt === null) firstFailureAt = Date.now();
            if (Date.now() - firstFailureAt >= POLL_MAX_FAILURE_MS) throw error;
            continue;
        }
        firstFailureAt = null;
        if (RETRYABLE_STATUSES.includes(response.status)) continue;
        if (!response.ok) return { ok: false, data: body };
        if (body.status === "done") return { ok: body.http_status < 400, data: body.result };
    }
    return { ok: false, data: { error: "The analysis is taking too long. Please try again." } };
}

// True only for absolute http:// or https:// URLs (rejects javascript:, data:, file:, etc.).
function isSafeHttpUrl(url) {
    try {
        const protocol = new URL(url).protocol;
        return protocol === "http:" || protocol === "https:";
    } catch {
        return false;
    }
}

function scoreTierClass(score) {
    if (score >= 70) return "score-high";
    if (score >= 45) return "score-mid";
    return "score-low";
}

function buildJobCard(job) {
    const card = createEl("div", "job-card");

    const titleRow = createEl("div", "job-title-row");
    titleRow.appendChild(createEl("h3", "job-title", job.title));
    titleRow.appendChild(createEl("span", `score-pill ${scoreTierClass(job.match_score)}`, `${job.match_score}% match`));
    card.appendChild(titleRow);

    card.appendChild(createEl(
        "p", "job-meta",
        `${job.company} — ${job.location || "Location not specified"} (via ${job.source})`
    ));

    card.appendChild(createEl(
        "p", "experience-compat",
        `Experience Compatibility: ${job.experience_compatibility}`
    ));

    const matchedWrap = createEl("div", "skills-block");
    matchedWrap.appendChild(createEl("strong", null, "Matched Skills"));
    const matchedChips = createEl("div", "chip-row");
    // skills_listed is false when the posting (often just a short snippet) names no skills.
    const unlisted = job.skills_listed === false;
    renderChips(matchedChips, job.matched_skills, "chip-success",
        unlisted ? "None of your skills appear in the posting text" : "None of the posting's skills match yours");
    matchedWrap.appendChild(matchedChips);
    card.appendChild(matchedWrap);

    const missingWrap = createEl("div", "skills-block");
    missingWrap.appendChild(createEl("strong", null, "Missing Skills"));
    const missingChips = createEl("div", "chip-row");
    renderChips(missingChips, job.missing_skills, "chip-danger",
        unlisted ? "This posting doesn't list its required skills" : "None");
    missingWrap.appendChild(missingChips);
    card.appendChild(missingWrap);

    card.appendChild(createEl("p", "why-matches", job.why_it_matches));

    // Job URLs come from external APIs, so only http(s) links get an Apply button.
    if (isSafeHttpUrl(job.url)) {
        const applyLink = document.createElement("a");
        applyLink.href = job.url;
        applyLink.target = "_blank";
        applyLink.rel = "noopener noreferrer";
        applyLink.className = "apply-btn";
        applyLink.textContent = "Apply Now →";
        card.appendChild(applyLink);
    }

    return card;
}

function displayRecommendations(recommendations) {
    recommendationsSection.innerHTML = "";

    if (recommendations.length === 0) {
        const empty = createEl("div", "card empty-state", "No matching jobs were found this time.");
        recommendationsSection.appendChild(empty);
        return;
    }

    const heading = createEl("h2", "recommendations-heading", `${recommendations.length} Job Recommendations`);
    recommendationsSection.appendChild(heading);

    recommendations.forEach((job, index) => {
        const card = buildJobCard(job);
        card.style.animationDelay = `${index * 60}ms`;
        recommendationsSection.appendChild(card);
    });

    recommendationsSection.scrollIntoView({ behavior: "smooth", block: "start" });
}

analyzeButton.addEventListener("click", async () => {
    const selectedFile = resumeInput.files[0];

    if (!selectedFile) {
        statusMessage.textContent = "Please choose a PDF or DOCX file first.";
        statusMessage.classList.add("error");
        return;
    }

    analyzeButton.disabled = true;
    analyzeButton.textContent = "Analyzing...";

    profileSection.classList.add("hidden");
    recommendationsSection.innerHTML = "";
    statusMessage.textContent = "Analyzing resume and searching for jobs... this may take 1-3 minutes.";
    statusMessage.classList.remove("error");
    statusMessage.classList.add("loading");

    startSimulatedProgress();

    try {
        // Read the file into memory before uploading. On Android the browser otherwise streams it
        // from the file picker's reference, which fails with a network error if the file came from
        // Drive/Downloads and can't be re-read at upload time (and makes retries unreliable).
        let fileBytes;
        try {
            fileBytes = await selectedFile.arrayBuffer();
        } catch (readError) {
            finishProgress();
            statusMessage.textContent = "Could not read that file. Please save it to your device and choose it again.";
            statusMessage.classList.remove("loading");
            statusMessage.classList.add("error");
            return;
        }
        const formData = new FormData();
        formData.append("resume", new Blob([fileBytes], { type: selectedFile.type }), selectedFile.name);

        const { ok, data } = await analyzeResume(formData);

        finishProgress();

        if (!ok) {
            statusMessage.textContent = "Error: " + data.error;
            statusMessage.classList.remove("loading");
            statusMessage.classList.add("error");
            return;
        }

        statusMessage.textContent = "";
        statusMessage.classList.remove("loading");
        displayProfile(data.candidate_profile);
        updateJobSourcesStep(data.search_via, data.search_via_reason);
        displaySearchVia(data.search_via, data.search_via_reason);
        displayRecommendations(data.recommendations);

    } catch (error) {
        finishProgress();
        statusMessage.textContent = "Could not reach the backend. Check your connection and try again - the server may have been asleep and needs a minute to wake up.";
        statusMessage.classList.remove("loading");
        statusMessage.classList.add("error");
    } finally {
        analyzeButton.disabled = false;
        analyzeButton.textContent = "Analyze Resume →";
    }
});
