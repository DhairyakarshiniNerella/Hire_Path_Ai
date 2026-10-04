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
    { id: "job_sources", icon: "🌐", label: "Searching jobs across multiple sources" },
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
function renderChips(container, items, chipClass) {
    container.innerHTML = "";
    container.classList.add("chip-row");

    if (!items || items.length === 0) {
        container.classList.remove("chip-row");
        container.textContent = "Not specified";
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

function createEl(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
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
    renderChips(matchedChips, job.matched_skills, "chip-success");
    matchedWrap.appendChild(matchedChips);
    card.appendChild(matchedWrap);

    const missingWrap = createEl("div", "skills-block");
    missingWrap.appendChild(createEl("strong", null, "Missing Skills"));
    const missingChips = createEl("div", "chip-row");
    renderChips(missingChips, job.missing_skills, "chip-danger");
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

    const formData = new FormData();
    formData.append("resume", selectedFile);

    try {
        const response = await fetch(`${API_BASE_URL}/api/resume/upload`, {
            method: "POST",
            body: formData,
        });
        const data = await response.json();

        finishProgress();

        if (!response.ok) {
            statusMessage.textContent = "Error: " + data.error;
            statusMessage.classList.remove("loading");
            statusMessage.classList.add("error");
            return;
        }

        statusMessage.textContent = "";
        statusMessage.classList.remove("loading");
        displayProfile(data.candidate_profile);
        displayRecommendations(data.recommendations);

    } catch (error) {
        finishProgress();
        statusMessage.textContent = "Could not reach the backend. Is Flask running?";
        statusMessage.classList.remove("loading");
        statusMessage.classList.add("error");
    } finally {
        analyzeButton.disabled = false;
        analyzeButton.textContent = "Analyze Resume →";
    }
});
