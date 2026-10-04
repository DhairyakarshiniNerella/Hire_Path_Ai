// Randomized stress tests for the browser code: 1000 seeded cases per phase.
// Each phase uses its own seeded generator, so a failure reproduces exactly (the assertion
// message names the phase, case number and the input that broke).
import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";
import { loadApp } from "./loadApp.js";

const N = 1000;

function prng(seed) {
  // mulberry32
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const pick = (r, list) => list[Math.floor(r() * list.length)];
const int = (r, lo, hi) => lo + Math.floor(r() * (hi - lo + 1));

const XSS = [
  "<script>window.__xss=1</script>", "<img src=x onerror=window.__xss=1>", "<svg onload=window.__xss=1>",
  "\"><iframe src=javascript:window.__xss=1>", "<b>bold</b>", "&lt;b&gt;", "'; DROP TABLE jobs;--", "{{7*7}}", "${7*7}",
];
const WORDS = ["Python", "C++", "", " ", "日本語", "😀", "x".repeat(2000), "Senior Engineer", "O'Brien", "a\nb", "\t", "0", "null", "undefined"];
const text = (r) => (r() < 0.25 ? pick(r, XSS) : pick(r, WORDS));

beforeAll(() => {
  vi.stubGlobal("fetch", () => Promise.resolve({ ok: false, json: () => Promise.resolve({}) }));
  loadApp();
});

afterEach(() => {
  vi.useRealTimers();
  delete globalThis.__xss;
});

const noInjectedElements = (root, label) => {
  expect(root.querySelectorAll("script, img, iframe, svg, style, object, embed, form, input").length, label).toBe(0);
  expect(globalThis.__xss, label).toBeUndefined();
};

// ---------------------------------------------------------------- phase F1: safe links

describe("phase F1: isSafeHttpUrl", () => {
  it("accepts only absolute http(s) URLs over 1000 random inputs", () => {
    const r = prng(101);
    const bad = ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "  javascript:alert(1)", "java\tscript:alert(1)", "java\nscript:alert(1)",
      "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)", "file:///etc/passwd", "ftp://example.com", "mailto:a@b.c",
      "//example.com/path", "/relative/path", "relative/path", "", "   ", "http", "https", "http:", "://x", "about:blank", "blob:https://x/1"];
    for (let i = 0; i < N; i++) {
      const label = `F1 case ${i}`;
      if (r() < 0.5) {
        const scheme = pick(r, ["http", "https", "HTTP", "HTTPS", "Https"]);
        const url = `${scheme}://${pick(r, ["example.com", "a.b.co", "localhost:3000", "[::1]", "x.org"])}${pick(r, ["", "/", "/job/1", "/a?b=c&d=e", "/#frag"])}`;
        expect(globalThis.isSafeHttpUrl(url), `${label}: ${url}`).toBe(true);
      } else {
        const url = r() < 0.7 ? pick(r, bad) : Array.from({ length: int(r, 0, 30) }, () => String.fromCharCode(int(r, 0, 300))).join("");
        const result = globalThis.isSafeHttpUrl(url);
        if (result) expect(/^\s*https?:\/\//i.test(url.replace(/[\t\n\r]/g, "")), `${label}: ${JSON.stringify(url)} accepted`).toBe(true);
        if (bad.includes(url)) expect(result, `${label}: ${JSON.stringify(url)}`).toBe(false);
      }
    }
    for (const nonString of [undefined, null, 0, {}, [], NaN]) expect(globalThis.isSafeHttpUrl(nonString)).toBe(false);
  });
});

// ---------------------------------------------------------------- phase F2: score colours

describe("phase F2: scoreTierClass", () => {
  it("always returns one of three classes and is monotonic over 1000 numbers", () => {
    const r = prng(102);
    const rank = { "score-low": 0, "score-mid": 1, "score-high": 2 };
    const values = [];
    for (let i = 0; i < N; i++) values.push(pick(r, [NaN, Infinity, -Infinity, -5, 0, 44.9, 45, 69.9, 70, 100, 1e9]) * (r() < 0.5 ? 1 : 1) + (r() < 0.5 ? 0 : Math.floor(r() * 130) - 10));
    for (const v of values) expect(Object.keys(rank), `F2 ${v}`).toContain(globalThis.scoreTierClass(v));
    const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
    for (let i = 1; i < sorted.length; i++) {
      expect(rank[globalThis.scoreTierClass(sorted[i])], `F2 monotonic at ${sorted[i]}`).toBeGreaterThanOrEqual(rank[globalThis.scoreTierClass(sorted[i - 1])]);
    }
  });
});

// ---------------------------------------------------------------- phase F3: chips

describe("phase F3: renderChips", () => {
  it("renders every item as plain text over 1000 random lists", () => {
    const r = prng(103);
    for (let i = 0; i < N; i++) {
      const items = r() < 0.15 ? pick(r, [null, undefined, []]) : Array.from({ length: int(r, 0, 25) }, () => (r() < 0.1 ? pick(r, [null, 0, 7]) : text(r)));
      const container = document.createElement("div");
      const emptyText = pick(r, ["Not specified", "None", "custom empty text"]);
      globalThis.renderChips(container, items, "chip-test", emptyText);
      const label = `F3 case ${i}: ${JSON.stringify(items)?.slice(0, 120)}`;
      noInjectedElements(container, label);
      if (!items || items.length === 0) {
        expect(container.textContent, label).toBe(emptyText);
        expect(container.querySelectorAll(".chip").length, label).toBe(0);
      } else {
        const chips = container.querySelectorAll(".chip");
        expect(chips.length, label).toBe(items.length);
        chips.forEach((chip, k) => expect(chip.textContent, label).toBe(items[k] === null || items[k] === undefined ? "" : String(items[k])));
      }
    }
  });
});

// ---------------------------------------------------------------- phase F4: job cards

const randomJob = (r) => {
  const job = {
    title: text(r), company: text(r), location: r() < 0.3 ? "" : text(r), source: pick(r, ["Adzuna", "Jooble", "Arbeitnow", text(r)]),
    match_score: pick(r, [0, 39, 40, 55, 70, 100, NaN, 12.5]), experience_compatibility: pick(r, ["Unknown", "Low", "Compatible", "Overqualified", text(r)]),
    matched_skills: Array.from({ length: int(r, 0, 8) }, () => text(r)), missing_skills: Array.from({ length: int(r, 0, 8) }, () => text(r)),
    why_it_matches: text(r), url: r() < 0.4 ? "https://example.com/job" : pick(r, ["javascript:window.__xss=1", "data:text/html,x", "", undefined, "ftp://x", text(r)]),
    skills_listed: pick(r, [true, false, undefined]),
  };
  return job;
};

describe("phase F4: buildJobCard", () => {
  it("never throws and never injects markup over 1000 random jobs", () => {
    const r = prng(104);
    for (let i = 0; i < N; i++) {
      const job = randomJob(r);
      const label = `F4 case ${i}: ${JSON.stringify(job).slice(0, 160)}`;
      let card;
      expect(() => { card = globalThis.buildJobCard(job); }, label).not.toThrow();
      noInjectedElements(card, label);
      expect(card.querySelector(".job-title").textContent, label).toBe(job.title);
      expect(card.querySelector(".score-pill").textContent, label).toBe(`${job.match_score}% match`);
      const link = card.querySelector(".apply-btn");
      if (globalThis.isSafeHttpUrl(job.url)) {
        expect(link, label).not.toBeNull();
        expect(link.getAttribute("rel"), label).toBe("noopener noreferrer");
        expect(link.getAttribute("target"), label).toBe("_blank");
        expect(/^https?:/i.test(link.href), label).toBe(true);
      } else {
        expect(link, `${label}: unsafe URL got an Apply button`).toBeNull();
      }
      expect(card.querySelectorAll("a[href^='javascript' i]").length, label).toBe(0);
      const unlisted = job.skills_listed === false;
      const blocks = card.querySelectorAll(".skills-block");
      expect(blocks.length, label).toBe(2);
      if (job.matched_skills.length === 0) expect(blocks[0].textContent, label).toContain(unlisted ? "None of your skills appear" : "None of the posting's skills match yours");
      if (job.missing_skills.length === 0) expect(blocks[1].textContent, label).toContain(unlisted ? "doesn't list its required skills" : "None");
    }
  });
});

// ---------------------------------------------------------------- phase F5: banner, profile, results

describe("phase F5: banner, profile and results", () => {
  it("handles every search_via value (1000 random)", () => {
    const r = prng(105);
    for (let i = 0; i < N; i++) {
      const value = pick(r, ["mcp", "direct", null, undefined, "", "other", 0, text(r)]);
      document.getElementById("search-via-note").classList.add("hidden");
      globalThis.displaySearchVia(value);
      const note = document.getElementById("search-via-note");
      const label = `F5 banner ${i}: ${JSON.stringify(value)}`;
      if (value === "mcp") { expect(note.textContent, label).toContain("MCP server"); expect(note.classList.contains("hidden"), label).toBe(false); }
      else if (value === "direct") { expect(note.textContent, label).toContain("directly"); expect(note.classList.contains("hidden"), label).toBe(false); }
      else expect(note.classList.contains("hidden"), label).toBe(true);
    }
  });

  it("renders realistic profiles as plain text (1000 random)", () => {
    const r = prng(106);
    for (let i = 0; i < N; i++) {
      const profile = {
        name: r() < 0.2 ? pick(r, [null, ""]) : text(r), career_level: r() < 0.2 ? null : pick(r, ["Fresher", "Entry Level", "Mid Level", "Senior", text(r)]),
        education: Array.from({ length: int(r, 0, 3) }, () => text(r)), skills: Array.from({ length: int(r, 0, 20) }, () => text(r)),
        total_experience_years: pick(r, [0, 0.5, 1.5, 8, 25]), target_roles: Array.from({ length: int(r, 0, 4) }, () => text(r)),
        projects: Array.from({ length: int(r, 0, 6) }, () => ({ name: text(r), description: r() < 0.3 ? "" : text(r) })),
      };
      const label = `F5 profile ${i}`;
      expect(() => globalThis.displayProfile(profile), label).not.toThrow();
      noInjectedElements(document.getElementById("profile-section"), label);
      expect(document.getElementById("profile-name").textContent, label).toBe(profile.name || "Unknown");
      expect(document.getElementById("profile-career-level").textContent, label).toBe(profile.career_level || "Unknown");
      expect(document.getElementById("profile-experience").textContent, label).toBe(`${profile.total_experience_years} year(s)`);
      expect(document.getElementById("profile-section").classList.contains("hidden"), label).toBe(false);
      expect(document.querySelectorAll("#profile-projects .project-item").length, label).toBe(profile.projects.length);
    }
  });

  it("renders any number of recommendations (1000 random lists)", () => {
    const r = prng(107);
    const section = document.getElementById("recommendations-section");
    for (let i = 0; i < N; i++) {
      const jobs = Array.from({ length: pick(r, [0, 0, 1, 2, 5, 10, 25]) }, () => randomJob(r));
      const label = `F5 results ${i}: ${jobs.length} jobs`;
      expect(() => globalThis.displayRecommendations(jobs), label).not.toThrow();
      noInjectedElements(section, label);
      if (jobs.length === 0) expect(section.textContent, label).toContain("No matching jobs were found");
      else {
        expect(section.querySelectorAll(".job-card").length, label).toBe(jobs.length);
        expect(section.querySelector(".recommendations-heading").textContent, label).toBe(`${jobs.length} Job Recommendations`);
      }
    }
  });
});

// ---------------------------------------------------------------- phase F6: start-and-poll protocol

const resp = (status, body, { badJson = false } = {}) => Promise.resolve({
  ok: status >= 200 && status < 300, status,
  json: () => (badJson ? Promise.reject(new SyntaxError("not json")) : Promise.resolve(body)),
});

describe("phase F6: analyzeResume protocol", () => {
  it("matches an oracle for 1000 random server behaviours", async () => {
    const r = prng(108);
    const outcomes = { ok: 0, notOk: 0, threw: 0 };
    for (let i = 0; i < N; i++) {
      vi.useFakeTimers();
      // start phase: k bad attempts first (network error / HTML 502-504), or a hard 400, or never up
      const startMode = pick(r, ["ok", "ok", "ok", "wake", "wake", "reject400", "never"]);
      const badAttempts = startMode === "wake" ? int(r, 1, 6) : 0;
      // poll phase
      const pollMode = pick(r, ["done200", "done200", "done502", "done500", "unknown404", "blips", "outage", "stuck"]);
      const runningPolls = int(r, 0, 5);
      const blips = pollMode === "blips" ? int(r, 1, 10) : 0;
      let startCalls = 0;
      let pollCalls = 0;
      const result = { status: "ok", marker: i };

      globalThis.fetch = (url) => {
        if (String(url).endsWith("/api/resume/start")) {
          startCalls += 1;
          if (startMode === "reject400") return resp(400, { error: "bad file" });
          if (startMode === "never" || (startMode === "wake" && startCalls <= badAttempts)) {
            return pick(r, [0, 1]) ? Promise.reject(new TypeError("Failed to fetch")) : resp(pick(r, [502, 503, 504]), null, { badJson: true });
          }
          return resp(202, { job_id: "job-1" });
        }
        pollCalls += 1;
        if (pollMode === "outage") return Promise.reject(new TypeError("Failed to fetch"));
        if (pollMode === "blips" && pollCalls <= blips) return pick(r, [0, 1]) ? Promise.reject(new TypeError("offline")) : resp(502, null, { badJson: true });
        if (pollMode === "unknown404") return resp(404, { error: "Unknown or expired job" });
        if (pollMode === "stuck" || pollCalls <= runningPolls + blips) return resp(200, { status: "running" });
        const status = pollMode === "done502" ? 502 : pollMode === "done500" ? 500 : 200;
        return resp(200, { status: "done", http_status: status, result: status === 200 ? result : { error: "agent failed" } });
      };

      const promise = globalThis.analyzeResume(new FormData()).then((value) => ({ value }), (error) => ({ error }));
      await vi.runAllTimersAsync();
      const settled = await promise;
      vi.useRealTimers();

      const label = `F6 case ${i}: start=${startMode}(${badAttempts}) poll=${pollMode}(running ${runningPolls}, blips ${blips})`;
      if (startMode === "never") { expect(settled.error, label).toBeInstanceOf(Error); outcomes.threw += 1; continue; }
      if (startMode === "reject400") { expect(settled.value, label).toEqual({ ok: false, data: { error: "bad file" } }); outcomes.notOk += 1; continue; }
      if (pollMode === "outage") { expect(settled.error, label).toBeInstanceOf(Error); outcomes.threw += 1; continue; }
      expect(settled.error, label).toBeUndefined();
      if (pollMode === "stuck") { expect(settled.value.ok, label).toBe(false); expect(settled.value.data.error, label).toContain("too long"); outcomes.notOk += 1; }
      else if (pollMode === "unknown404") { expect(settled.value, label).toEqual({ ok: false, data: { error: "Unknown or expired job" } }); outcomes.notOk += 1; }
      else if (pollMode === "done502" || pollMode === "done500") { expect(settled.value, label).toEqual({ ok: false, data: { error: "agent failed" } }); outcomes.notOk += 1; }
      else { expect(settled.value, label).toEqual({ ok: true, data: result }); outcomes.ok += 1; }
    }
    // every kind of outcome was actually exercised
    expect(outcomes.ok).toBeGreaterThan(100);
    expect(outcomes.notOk).toBeGreaterThan(100);
    expect(outcomes.threw).toBeGreaterThan(50);
  }, 120000);
});
