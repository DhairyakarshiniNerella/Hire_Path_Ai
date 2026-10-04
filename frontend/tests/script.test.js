import { describe, it, expect, beforeAll, beforeEach, afterEach, vi } from "vitest";
import { loadApp } from "./loadApp.js";

function fakeFetchResponse(ok, jsonData) {
  return Promise.resolve({
    ok,
    json: () => Promise.resolve(jsonData),
  });
}

beforeAll(() => {
  vi.stubGlobal("fetch", () => fakeFetchResponse(false, {}));
  loadApp();
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

// ---------- scoreTierClass ----------

describe("scoreTierClass", () => {
  it("classifies high scores", () => {
    expect(globalThis.scoreTierClass(70)).toBe("score-high");
    expect(globalThis.scoreTierClass(95)).toBe("score-high");
  });

  it("classifies mid scores", () => {
    expect(globalThis.scoreTierClass(45)).toBe("score-mid");
    expect(globalThis.scoreTierClass(69)).toBe("score-mid");
  });

  it("classifies low scores", () => {
    expect(globalThis.scoreTierClass(0)).toBe("score-low");
    expect(globalThis.scoreTierClass(44)).toBe("score-low");
  });
});

// ---------- renderChips ----------

describe("renderChips", () => {
  it("renders one chip per item", () => {
    const container = document.createElement("div");
    globalThis.renderChips(container, ["Python", "SQL"], "chip-neutral");

    const chips = container.querySelectorAll(".chip");
    expect(chips.length).toBe(2);
    expect(chips[0].textContent).toBe("Python");
    expect(chips[0].className).toBe("chip chip-neutral");
  });

  it("shows 'Not specified' for an empty list", () => {
    const container = document.createElement("div");
    globalThis.renderChips(container, [], "chip-neutral");
    expect(container.textContent).toBe("Not specified");
  });

  it("shows 'Not specified' for null/undefined", () => {
    const container = document.createElement("div");
    globalThis.renderChips(container, null, "chip-neutral");
    expect(container.textContent).toBe("Not specified");
  });
});

// ---------- renderProjects ----------

describe("renderProjects", () => {
  it("renders a name and description for each project", () => {
    const container = document.createElement("div");
    globalThis.renderProjects(container, [
      { name: "HirePath AI", description: "Job matching system" },
    ]);

    expect(container.querySelector(".project-name").textContent).toBe("HirePath AI");
    expect(container.querySelector(".project-desc").textContent).toBe("Job matching system");
  });

  it("omits the description element when there is none", () => {
    const container = document.createElement("div");
    globalThis.renderProjects(container, [{ name: "Tool", description: "" }]);

    expect(container.querySelector(".project-name")).not.toBeNull();
    expect(container.querySelector(".project-desc")).toBeNull();
  });

  it("shows 'Not specified' when there are no projects", () => {
    const container = document.createElement("div");
    globalThis.renderProjects(container, []);
    expect(container.textContent).toBe("Not specified");
  });
});

// ---------- displayProfile ----------

describe("displayProfile", () => {
  it("fills in every profile field", () => {
    globalThis.displayProfile({
      name: "Jane Doe",
      career_level: "Mid Level",
      education: ["B.Tech CS"],
      skills: ["Python", "SQL"],
      total_experience_years: 2.5,
      projects: [{ name: "Tool", description: "Does things" }],
      target_roles: ["Backend Developer"],
    });

    expect(document.getElementById("profile-name").textContent).toBe("Jane Doe");
    expect(document.getElementById("profile-career-level").textContent).toBe("Mid Level");
    expect(document.getElementById("profile-education").textContent).toBe("B.Tech CS");
    expect(document.getElementById("profile-experience").textContent).toBe("2.5 year(s)");
    expect(document.getElementById("profile-target-roles").textContent).toBe("Backend Developer");
    expect(document.getElementById("profile-section").classList.contains("hidden")).toBe(false);
  });

  it("falls back to 'Unknown'/'Not specified' for missing data", () => {
    globalThis.displayProfile({
      name: null,
      career_level: null,
      education: [],
      skills: [],
      total_experience_years: 0,
      projects: [],
      target_roles: [],
    });

    expect(document.getElementById("profile-name").textContent).toBe("Unknown");
    expect(document.getElementById("profile-career-level").textContent).toBe("Unknown");
    expect(document.getElementById("profile-education").textContent).toBe("Not specified");
    expect(document.getElementById("profile-target-roles").textContent).toBe("Not specified");
  });
});

// ---------- buildJobCard / displayRecommendations ----------

describe("buildJobCard", () => {
  const job = {
    title: "Backend Developer",
    company: "Acme",
    location: "Remote",
    source: "Adzuna",
    match_score: 82,
    experience_compatibility: "Compatible",
    matched_skills: ["Python"],
    missing_skills: ["Docker"],
    why_it_matches: "Great fit because of Python skills.",
    url: "https://example.com/job/1",
  };

  it("renders the title, score pill, and meta line", () => {
    const card = globalThis.buildJobCard(job);
    expect(card.querySelector(".job-title").textContent).toBe("Backend Developer");
    expect(card.querySelector(".score-pill").textContent).toBe("82% match");
    expect(card.querySelector(".score-pill").className).toContain("score-high");
    expect(card.querySelector(".job-meta").textContent).toBe("Acme — Remote (via Adzuna)");
  });

  it("falls back to 'Location not specified' when location is missing", () => {
    const card = globalThis.buildJobCard({ ...job, location: "" });
    expect(card.querySelector(".job-meta").textContent).toContain("Location not specified");
  });

  it("builds an apply link that opens in a new tab safely", () => {
    const card = globalThis.buildJobCard(job);
    const link = card.querySelector(".apply-btn");
    expect(link.href).toBe(job.url);
    expect(link.target).toBe("_blank");
    expect(link.rel).toBe("noopener noreferrer");
  });

  it("allows http and https apply links", () => {
    for (const url of ["http://example.com/job", "https://example.com/job"]) {
      expect(globalThis.buildJobCard({ ...job, url }).querySelector(".apply-btn")).not.toBeNull();
    }
  });

  it("omits the apply button for unsafe or invalid URLs", () => {
    const unsafe = [
      "javascript:alert(1)",
      "JavaScript:alert(1)",
      "data:text/html,<script>alert(1)</script>",
      "file:///C:/secret.txt",
      "ftp://example.com/job",
      "/relative/path",
      "",
      undefined,
    ];
    for (const url of unsafe) {
      expect(globalThis.buildJobCard({ ...job, url }).querySelector(".apply-btn")).toBeNull();
    }
  });
});

describe("displayRecommendations", () => {
  it("shows an empty state when there are no recommendations", () => {
    globalThis.displayRecommendations([]);
    const recommendationsSection = document.getElementById("recommendations-section");
    expect(recommendationsSection.querySelector(".empty-state")).not.toBeNull();
    expect(recommendationsSection.querySelectorAll(".job-card").length).toBe(0);
  });

  it("renders one card per recommendation with a heading", () => {
    globalThis.displayRecommendations([
      { title: "Job A", company: "A Co", source: "Adzuna", match_score: 90, matched_skills: [], missing_skills: [], why_it_matches: "x", url: "#" },
      { title: "Job B", company: "B Co", source: "Jooble", match_score: 60, matched_skills: [], missing_skills: [], why_it_matches: "y", url: "#" },
    ]);
    const recommendationsSection = document.getElementById("recommendations-section");
    expect(recommendationsSection.querySelector(".recommendations-heading").textContent).toBe("2 Job Recommendations");
    expect(recommendationsSection.querySelectorAll(".job-card").length).toBe(2);
  });
});

// ---------- theme toggle ----------

describe("theme toggle", () => {
  it("applyTheme sets the data-theme attribute and button icon", () => {
    globalThis.applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.getElementById("theme-toggle").textContent).toBe("☀️");

    globalThis.applyTheme("light");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.getElementById("theme-toggle").textContent).toBe("🌙");
  });

  it("clicking the toggle button flips the theme and persists it", () => {
    document.documentElement.setAttribute("data-theme", "light");
    const button = document.getElementById("theme-toggle");

    button.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("hirepath-theme")).toBe("dark");

    button.click();
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("hirepath-theme")).toBe("light");
  });
});

// ---------- file selection display ----------

describe("showSelectedFileName", () => {
  it("shows the chosen file's name", () => {
    const input = document.getElementById("resume-input");
    Object.defineProperty(input, "files", {
      value: [{ name: "my-resume.pdf" }],
      configurable: true,
    });

    globalThis.showSelectedFileName();

    expect(document.getElementById("file-drop-label").textContent).toBe("Selected: my-resume.pdf");
  });

  it("reverts to the placeholder text when no file is selected", () => {
    const input = document.getElementById("resume-input");
    Object.defineProperty(input, "files", { value: [], configurable: true });

    globalThis.showSelectedFileName();

    expect(document.getElementById("file-drop-label").textContent).toContain("Drag & drop your resume");
  });
});

// ---------- backend status check ----------

describe("checkBackendStatus", () => {
  it("shows online when the health check succeeds", async () => {
    vi.stubGlobal("fetch", () => fakeFetchResponse(true, { status: "ok" }));
    await globalThis.checkBackendStatus();

    expect(document.getElementById("backend-status-text").textContent).toBe("Backend online");
    expect(document.getElementById("backend-status-dot").className).toContain("status-online");
  });

  it("shows offline when the health check fails", async () => {
    vi.stubGlobal("fetch", () => Promise.reject(new Error("network down")));
    await globalThis.checkBackendStatus();

    expect(document.getElementById("backend-status-text").textContent).toBe("Backend offline");
    expect(document.getElementById("backend-status-dot").className).toContain("status-offline");
  });

  it("shows offline when the response is not ok", async () => {
    vi.stubGlobal("fetch", () => fakeFetchResponse(false, {}));
    await globalThis.checkBackendStatus();

    expect(document.getElementById("backend-status-text").textContent).toBe("Backend offline");
  });
});

// ---------- agent progress checklist ----------

describe("agent progress checklist", () => {
  it("renderAgentChecklist creates one pending item per agent", () => {
    globalThis.renderAgentChecklist();
    const items = document.querySelectorAll("#agent-progress-list li");
    expect(items.length).toBe(6);
    items.forEach((item) => expect(item.className).toBe("agent-pending"));
    expect(document.getElementById("progress-bar-fill").style.width).toBe("0%");
  });

  it("shows one honest job-sources step instead of per-source agents", () => {
    globalThis.renderAgentChecklist();
    const text = document.getElementById("agent-progress-list").textContent;

    expect(text).toContain("Fetching jobs through the MCP server");
    for (const name of ["Adzuna Agent", "Jooble Agent", "Arbeitnow Agent"]) {
      expect(text).not.toContain(name);
    }
  });

  it("markAgentDone marks one item done and updates the progress bar", () => {
    globalThis.renderAgentChecklist();
    globalThis.markAgentDone("resume_analyzer");

    const item = document.getElementById("agent-item-resume_analyzer");
    expect(item.className).toBe("agent-done");
    expect(document.getElementById("progress-bar-fill").style.width).toBe("17%");
  });

  it("markAgentDone is a no-op if the same agent is marked twice", () => {
    globalThis.renderAgentChecklist();
    globalThis.markAgentDone("resume_analyzer");
    globalThis.markAgentDone("resume_analyzer");

    expect(document.getElementById("progress-bar-fill").style.width).toBe("17%");
  });

  it("finishProgress marks every agent done immediately", () => {
    globalThis.renderAgentChecklist();
    globalThis.finishProgress();

    const doneItems = document.querySelectorAll("#agent-progress-list li.agent-done");
    expect(doneItems.length).toBe(6);
    expect(document.getElementById("progress-bar-fill").style.width).toBe("100%");
  });
});

// ---------- analyze button click flow ----------

function selectFile(name = "resume.pdf") {
  const input = document.getElementById("resume-input");
  const file = { name, type: "application/pdf", arrayBuffer: async () => new ArrayBuffer(8) };
  Object.defineProperty(input, "files", { value: [file], configurable: true });
}

function selectUnreadableFile(name = "resume.pdf") {
  const input = document.getElementById("resume-input");
  const file = { name, type: "application/pdf", arrayBuffer: async () => { throw new Error("NotReadableError"); } };
  Object.defineProperty(input, "files", { value: [file], configurable: true });
}

function clearFile() {
  const input = document.getElementById("resume-input");
  Object.defineProperty(input, "files", { value: [], configurable: true });
}

describe("analyze button click flow", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  it("shows an error and makes no request when no file is selected", async () => {
    clearFile();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    document.getElementById("analyze-btn").click();
    await Promise.resolve();

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(document.getElementById("status-message").textContent).toBe(
      "Please choose a PDF or DOCX file first."
    );
    expect(document.getElementById("status-message").classList.contains("error")).toBe(true);
  });

  it("displays the profile and recommendations after starting and polling the analysis", async () => {
    selectFile();
    const result = {
      status: "ok",
      search_via: "mcp",
      candidate_profile: {
        name: "Jane Doe",
        career_level: "Mid Level",
        education: ["B.Tech CS"],
        skills: ["Python"],
        total_experience_years: 2,
        projects: [],
        target_roles: ["Backend Developer"],
      },
      recommendations: [
        { title: "Backend Dev", company: "Acme", source: "Adzuna", match_score: 90, matched_skills: [], missing_skills: [], why_it_matches: "great fit", url: "#" },
      ],
    };
    let polls = 0;
    vi.stubGlobal("fetch", (url) => {
      if (url.endsWith("/api/resume/start")) return fakeFetchResponse(true, { job_id: "abc" });
      polls += 1;
      return fakeFetchResponse(true, polls < 2
        ? { status: "running" }
        : { status: "done", http_status: 200, result });
    });

    document.getElementById("analyze-btn").click();
    await vi.advanceTimersByTimeAsync(3000);
    await vi.advanceTimersByTimeAsync(3000);

    await vi.waitFor(() => {
      expect(document.getElementById("profile-name").textContent).toBe("Jane Doe");
    });

    expect(polls).toBe(2);
    expect(document.getElementById("profile-section").classList.contains("hidden")).toBe(false);
    expect(document.querySelectorAll("#recommendations-section .job-card").length).toBe(1);
    expect(document.getElementById("search-via-note").textContent).toContain("MCP server");
    expect(document.getElementById("status-message").textContent).toBe("");
    expect(document.getElementById("analyze-btn").disabled).toBe(false);
    expect(document.getElementById("analyze-btn").textContent).toBe("Analyze Resume →");
  });

  it("shows the server's error message when the backend rejects the upload", async () => {
    selectFile();
    vi.stubGlobal("fetch", () => fakeFetchResponse(false, { error: "Only PDF and DOCX files are allowed" }));

    document.getElementById("analyze-btn").click();

    await vi.waitFor(() => {
      expect(document.getElementById("status-message").textContent).toBe(
        "Error: Only PDF and DOCX files are allowed"
      );
    });

    expect(document.getElementById("status-message").classList.contains("error")).toBe(true);
    expect(document.getElementById("analyze-btn").disabled).toBe(false);
  });

  it("shows the pipeline's error when the finished analysis failed", async () => {
    selectFile();
    vi.stubGlobal("fetch", (url) =>
      url.endsWith("/api/resume/start")
        ? fakeFetchResponse(true, { job_id: "abc" })
        : fakeFetchResponse(true, { status: "done", http_status: 502, result: { error: "Job Search Agent failed" } })
    );

    document.getElementById("analyze-btn").click();
    await vi.advanceTimersByTimeAsync(3000);

    await vi.waitFor(() => {
      expect(document.getElementById("status-message").textContent).toBe("Error: Job Search Agent failed");
    });
  });

  it("keeps polling through a few dropped requests", async () => {
    selectFile();
    let polls = 0;
    vi.stubGlobal("fetch", (url) => {
      if (url.endsWith("/api/resume/start")) return fakeFetchResponse(true, { job_id: "abc" });
      polls += 1;
      if (polls <= 2) return Promise.reject(new Error("blip"));
      return fakeFetchResponse(true, { status: "done", http_status: 200, result: { status: "ok", search_via: "mcp", candidate_profile: { name: "Jane Doe" }, recommendations: [] } });
    });

    document.getElementById("analyze-btn").click();
    for (let i = 0; i < 3; i++) await vi.advanceTimersByTimeAsync(3000);

    await vi.waitFor(() => {
      expect(document.getElementById("profile-name").textContent).toBe("Jane Doe");
    });
  });

  it("shows a connectivity message when the backend stays unreachable", async () => {
    selectFile();
    vi.stubGlobal("fetch", () => Promise.reject(new Error("network down")));

    document.getElementById("analyze-btn").click();
    for (let i = 0; i < 20; i++) await vi.advanceTimersByTimeAsync(5000);

    await vi.waitFor(() => {
      expect(document.getElementById("status-message").textContent).toContain("Could not reach the backend");
    });

    expect(document.getElementById("status-message").classList.contains("error")).toBe(true);
    expect(document.getElementById("analyze-btn").disabled).toBe(false);
  });

  it("tells the user when the chosen file cannot be read, without calling the backend", async () => {
    selectUnreadableFile();
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    document.getElementById("analyze-btn").click();

    await vi.waitFor(() => {
      expect(document.getElementById("status-message").textContent).toContain("Could not read that file");
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(document.getElementById("analyze-btn").disabled).toBe(false);
  });

  it("retries the start request while the backend wakes up (HTML 502 page)", async () => {
    selectFile();
    let starts = 0;
    vi.stubGlobal("fetch", (url) => {
      if (url.endsWith("/api/resume/start")) {
        starts += 1;
        if (starts <= 2) {
          return Promise.resolve({ ok: false, status: 502, json: () => Promise.reject(new SyntaxError("not json")) });
        }
        return fakeFetchResponse(true, { job_id: "abc" });
      }
      return fakeFetchResponse(true, { status: "done", http_status: 200, result: { status: "ok", search_via: "mcp", candidate_profile: { name: "Jane Doe" }, recommendations: [] } });
    });

    document.getElementById("analyze-btn").click();
    for (let i = 0; i < 4; i++) await vi.advanceTimersByTimeAsync(5000);

    await vi.waitFor(() => {
      expect(document.getElementById("profile-name").textContent).toBe("Jane Doe");
    });
    expect(starts).toBe(3);
  });

  it("keeps polling through a longer connection loss", async () => {
    selectFile();
    let polls = 0;
    vi.stubGlobal("fetch", (url) => {
      if (url.endsWith("/api/resume/start")) return fakeFetchResponse(true, { job_id: "abc" });
      polls += 1;
      if (polls <= 10) return Promise.reject(new Error("offline"));
      return fakeFetchResponse(true, { status: "done", http_status: 200, result: { status: "ok", search_via: "mcp", candidate_profile: { name: "Jane Doe" }, recommendations: [] } });
    });

    document.getElementById("analyze-btn").click();
    for (let i = 0; i < 12; i++) await vi.advanceTimersByTimeAsync(3000);

    await vi.waitFor(() => {
      expect(document.getElementById("profile-name").textContent).toBe("Jane Doe");
    });
  });

});
