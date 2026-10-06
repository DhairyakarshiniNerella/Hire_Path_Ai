"""
Randomized stress tests: 1000 seeded cases per phase of the pipeline.

Everything that calls an LLM or a job API is mocked, so these cost no tokens and run in
seconds. Each phase seeds its own random generator, so any failure reproduces exactly
(the assertion message names the phase, case number and the input that broke).

Phases
  1  resume file parsing            8  error-message translation
  2  experience calculation         9  supervisor routing
  3  experience-requirement parsing 10 Flask API (uploads, start/status jobs)
  4  job normalising / de-duping    11 MCP bearer-token auth
  5  MCP source clients             12 MCP client helpers (URL, wake-up, errors)
  6  MCP search tool                13 job-search agent (MCP / direct fallback)
  7  matching and ranking           14 whole pipeline, random failures at every stage
"""
import io
import json
import os
import random
import string
import threading
import time
from datetime import date
from types import SimpleNamespace

import pytest

N = 1000


def rng(phase):
    return random.Random(f"hirepath-stress-phase-{phase}")


# ---------------------------------------------------------------- random data helpers

TEXTS = [
    "", " ", "Python", "python ", "C++", "C#", "R", "Java", "JavaScript", "Node.js", "SQL (Postgres)",
    "(.*)[", "a|b", "\\", "日本語エンジニア", "😀 dev", "<script>alert(1)</script>", "x" * 3000,
    "tab\tnew\nline", "%s{0}{x}", "O'Brien", "Senior Engineer", "Berlin", "https://example.com/job/1",
]


def text(r, allow_nul=False):
    if r.random() < 0.6:
        value = r.choice(TEXTS)
    else:
        alphabet = string.printable if allow_nul else string.printable.replace("\x0b", "").replace("\x0c", "")
        value = "".join(r.choice(alphabet) for _ in range(r.randint(0, 40)))
    return value


def hostile(r):
    """A value an API might send instead of a string: null, a number, an empty container..."""
    return r.choice([None, None, 0, 1, -5, 2.5, True, [], {}, ["x"], {"display_name": None}, text(r)])


def field(r, name_value_factory, p_missing=0.1, p_hostile=0.2):
    roll = r.random()
    if roll < p_missing:
        return "__missing__"
    if roll < p_missing + p_hostile:
        return hostile(r)
    return name_value_factory()


def build(r, spec, p_missing=0.1, p_hostile=0.2):
    d = {}
    for key, factory in spec.items():
        v = field(r, factory, p_missing, p_hostile)
        if v != "__missing__":
            d[key] = v
    return d


# ================================================================ PHASE 1: resume files

def test_phase1_resume_file_parsing(tmp_path):
    from docx import Document
    from app.tools.resume_parser import extract_resume_text

    r = rng(1)
    kinds = ["missing", "badext", "garbage_pdf", "garbage_docx", "empty_pdf", "empty_docx",
             "trunc_docx", "ok_docx", "ok_docx", "blank_docx", "noext", "upper_ext"]
    for i in range(N):
        kind = r.choice(kinds)
        label = f"phase1 case {i} kind={kind}"
        path = tmp_path / f"f{i}"
        expect_text = None

        if kind == "missing":
            path = tmp_path / f"nope{i}.pdf"
        elif kind == "badext":
            path = tmp_path / f"f{i}.{r.choice(['txt', 'exe', 'doc', 'png', 'pdf.exe'])}"
            path.write_bytes(os.urandom(r.randint(0, 200)))
        elif kind in ("garbage_pdf", "garbage_docx"):
            path = tmp_path / f"f{i}.{'pdf' if kind == 'garbage_pdf' else 'docx'}"
            path.write_bytes(os.urandom(r.randint(1, 600)))
        elif kind in ("empty_pdf", "empty_docx"):
            path = tmp_path / f"f{i}.{'pdf' if kind == 'empty_pdf' else 'docx'}"
            path.write_bytes(b"")
        elif kind == "noext":
            path = tmp_path / f"resume{i}"
            path.write_bytes(b"hello")
        else:
            doc = Document()
            words = [w for w in (text(r).replace("\x00", "").replace("\r", "") for _ in range(r.randint(1, 8))) if w.strip()]
            if kind == "blank_docx":
                words = []
                doc.add_paragraph("   ")
            for w in words:
                doc.add_paragraph(w)
            ext = "DOCX" if kind == "upper_ext" else "docx"
            path = tmp_path / f"f{i}.{ext}"
            doc.save(path)
            if kind == "trunc_docx":
                data = path.read_bytes()
                path.write_bytes(data[: r.randint(1, max(1, len(data) - 1))])
            elif words:
                expect_text = words

        result = extract_resume_text(str(path))
        assert isinstance(result, dict) and isinstance(result.get("success"), bool), label
        if result["success"]:
            assert isinstance(result["text"], str) and result["text"].strip(), label
            if expect_text:
                for w in expect_text:
                    assert w.strip() in result["text"], f"{label}: lost text {w!r}"
        else:
            assert isinstance(result.get("error"), str) and result["error"], label
            assert kind not in ("ok_docx", "upper_ext") or not expect_text, f"{label}: valid file rejected"


# ================================================================ PHASE 2: experience maths

def _month(r, lo=2000, hi=2026):
    return f"{r.randint(lo, hi)}-{r.randint(1, 12):02d}"


def _oracle_years(periods, today):
    """Independent re-implementation: union of covered months, rounded half-up to 0.5."""
    covered = set()
    for start, end in periods:
        def idx(v):
            v = (v or "").strip().lower()
            if v in ("", "present", "current", "now", "till date", "ongoing"):
                return today.year * 12 + today.month
            try:
                y, m = v.split("-")[:2]
                y, m = int(y), int(m)
                return y * 12 + m if 1 <= m <= 12 else None
            except ValueError:
                return None
        s, e = idx(start), idx(end)
        if s is None or e is None or e < s:
            continue
        covered.update(range(s, e + 1))
    import math
    return math.floor(len(covered) / 12 * 2 + 0.5) / 2


def test_phase2_experience_calculation():
    from app.services.experience_calculator import calculate_full_time_years, career_level_for

    today = date(2026, 10, 4)
    r = rng(2)
    ends = lambda: r.choice([_month(r), _month(r), "", "Present", "current", "garbage", "2025-13", "abc-12", None, "2020-1-1"])
    for i in range(N):
        pairs = [(_month(r), ends()) for _ in range(r.randint(0, 7))]
        periods = [SimpleNamespace(start=s, end=e) for s, e in pairs]
        label = f"phase2 case {i}: {pairs}"
        got = calculate_full_time_years(periods, today=today)

        assert got == _oracle_years(pairs, today), label
        assert got >= 0 and (got * 2) == int(got * 2), label

        shuffled = periods[:]
        r.shuffle(shuffled)
        assert calculate_full_time_years(shuffled, today=today) == got, f"{label}: order mattered"
        assert calculate_full_time_years(periods + periods[:1], today=today) == got, f"{label}: duplicate counted"
        extra = SimpleNamespace(start=_month(r), end=_month(r))
        assert calculate_full_time_years(periods + [extra], today=today) >= got, f"{label}: adding a job lowered total"

        level = career_level_for(got)
        expected = "Fresher" if got <= 0 else "Entry Level" if got < 2 else "Mid Level" if got <= 5 else "Senior"
        assert level == expected, label


# ================================================================ PHASE 3: requirement parsing

def test_phase3_experience_requirement_parsing():
    from app.services.experience_parser import extract_experience_requirement as parse

    r = rng(3)
    noise = ["We are hiring a motivated engineer.", "Great benefits and remote work.", "Apply today!", "",
             "Responsibilities include building apis and writing tests."]
    for i in range(N):
        a = r.randint(0, 15)
        b = a + r.randint(0, 10)
        kind = r.choice(["range", "range_to", "range_dash", "plus", "minimum", "atleast", "fresher", "plain", "none"])
        phrase, want = {
            "range": (f"{a}-{b} years", (a, b)),
            "range_to": (f"{a} to {b} years", (a, b)),
            "range_dash": (f"{a}–{b} years", (a, b)),
            "plus": (f"{a}+ years", (a, None)),
            "minimum": (f"Minimum {a} years", (a, None)),
            "atleast": (f"at least {a} years of experience", (a, None)),
            "fresher": (r.choice(["Fresher", "entry level", "Entry-Level", "no experience required"]), (0, 0)),
            "plain": (f"{a} years", (a, a)),
            "none": ("", None),
        }[kind]
        if r.random() < 0.5:
            phrase = phrase.upper() if kind in ("range", "plus", "plain") else phrase
        body = f"{r.choice(noise)} {phrase}. {r.choice(noise)}"
        label = f"phase3 case {i}: {body!r}"
        got = parse(body)
        assert set(got) == {"raw_text", "min_years", "max_years"}, label
        if want is None:
            assert got["min_years"] is None and got["raw_text"] == "Unknown", label
        else:
            assert got["min_years"] == float(want[0]), label
            assert got["max_years"] == (None if want[1] is None else float(want[1])), label
            assert got["min_years"] is None or got["max_years"] is None or got["min_years"] <= got["max_years"], label

        # arbitrary garbage and reversed ranges must never raise
        junk = "".join(r.choice(string.printable + "日本–—") for _ in range(r.randint(0, 200)))
        out = parse(junk)
        assert set(out) == {"raw_text", "min_years", "max_years"}, f"phase3 junk {junk!r}"
    for odd in (None, "", "   ", "5-3 years", "99999999999999999999 years", "0 years"):
        assert set(parse(odd)) == {"raw_text", "min_years", "max_years"}


# ================================================================ PHASE 4: job normalising

RAW_SPECS = {
    "adzuna": {"title": lambda: "T", "company": lambda: {"display_name": "Co"}, "location": lambda: {"display_name": "Loc"},
               "description": lambda: "d", "redirect_url": lambda: "https://x", "id": lambda: "1", "contract_time": lambda: "full_time"},
    "jooble": {"title": lambda: "T", "company": lambda: "Co", "location": lambda: "Loc", "snippet": lambda: "d",
               "link": lambda: "https://x", "id": lambda: 99, "type": lambda: "Full-time"},
    "arbeitnow": {"title": lambda: "T", "company_name": lambda: "Co", "location": lambda: "Loc", "description": lambda: "d",
                  "url": lambda: "https://x", "slug": lambda: "s", "job_types": lambda: ["full_time"], "tags": lambda: ["python"]},
}
STR_KEYS = ("title", "company", "location", "description", "url", "source", "source_id", "employment_type")


def _raw_job(r):
    source = r.choice(["adzuna", "jooble", "arbeitnow"])
    raw = build(r, RAW_SPECS[source], p_missing=0.15, p_hostile=0.25)
    if r.random() < 0.9:
        raw["_source"] = source
    return raw


def test_phase4_job_normalizing_dedupe_balancing():
    from app.services.job_normalizer import normalize_jobs, remove_duplicate_jobs, select_balanced_jobs

    r = rng(4)
    for i in range(N):
        raws = [_raw_job(r) for _ in range(r.randint(0, 25))]
        label = f"phase4 case {i}"
        normalized = normalize_jobs(raws)
        for job in normalized:
            for key in STR_KEYS:
                assert isinstance(job[key], str), f"{label}: {key}={job[key]!r} from {raws}"
            assert job["skills_required"] == [] and job["experience_required"] == "Unknown", label

        # make a share of them duplicates to exercise the de-duper
        pool = normalized + [dict(j) for j in r.sample(normalized, k=min(len(normalized), r.randint(0, 5)))]
        r.shuffle(pool)
        unique = remove_duplicate_jobs(pool)
        keys = [(j["title"].strip().lower(), j["company"].strip().lower(), j["location"].strip().lower()) for j in unique]
        assert len(keys) == len(set(keys)), f"{label}: content duplicate survived"
        ids = [(j["source"], j["source_id"]) for j in unique if j["source_id"]]
        assert len(ids) == len(set(ids)), f"{label}: id duplicate survived"
        assert remove_duplicate_jobs(unique) == unique, f"{label}: not idempotent"
        positions = [pool.index(j) for j in unique]
        assert positions == sorted(positions), f"{label}: order changed"

        limit = r.randint(0, 20)
        picked = select_balanced_jobs(list(unique), limit)
        assert len(picked) == min(limit, len(unique)), label
        by_source = {}
        for j in unique:
            by_source.setdefault(j["source"], []).append(j)
        counts = {s: sum(1 for j in picked if j["source"] == s) for s in by_source}
        for a in counts:
            for b in counts:
                if counts[a] > counts[b] + 1:
                    assert counts[b] == len(by_source[b]), f"{label}: unfair pick {counts}"


# ================================================================ PHASE 5: MCP source clients

class FakeResponse:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _random_response(r, shape):
    status = r.choice([200, 200, 200, 200, 401, 403, 429, 500, 502, 404, 302])
    roll = r.random()
    if status != 200 or roll > 0.35:
        payload = shape(r)
    elif roll > 0.2:
        payload = ValueError("not json")
    elif roll > 0.1:
        payload = None
    else:
        payload = ["unexpected", "list"]
    return FakeResponse(status, payload)


def test_phase5_mcp_source_clients(monkeypatch):
    import requests
    from mcp_server import config
    from mcp_server.models import Job
    from mcp_server.services import adzuna, arbeitnow, jooble

    monkeypatch.setattr(config, "ADZUNA_APP_ID", "SECRET-APP-ID")
    monkeypatch.setattr(config, "ADZUNA_APP_KEY", "SECRET-APP-KEY")
    monkeypatch.setattr(config, "JOOBLE_API_KEY", "SECRET-JOOBLE-KEY")
    secrets = ("SECRET-APP-ID", "SECRET-APP-KEY", "SECRET-JOOBLE-KEY")

    r = rng(5)
    adz = lambda rr: {"results": [build(rr, RAW_SPECS["adzuna"], 0.15, 0.25) for _ in range(rr.randint(0, 6))]}
    joo = lambda rr: {"jobs": [build(rr, RAW_SPECS["jooble"], 0.15, 0.25) for _ in range(rr.randint(0, 6))]}
    arb = lambda rr: {"data": [build(rr, RAW_SPECS["arbeitnow"], 0.15, 0.25) for _ in range(rr.randint(0, 8))]}

    for i in range(N):
        which = r.choice(["adzuna", "jooble", "arbeitnow"])
        label = f"phase5 case {i} {which}"
        fail_kind = r.random()

        def fake_http(*a, **k):
            if fail_kind < 0.1:
                raise requests.exceptions.Timeout("took too long SECRET-JOOBLE-KEY")
            if fail_kind < 0.2:
                raise requests.exceptions.ConnectionError("boom https://jooble.org/api/SECRET-JOOBLE-KEY")
            return _random_response(r, {"adzuna": adz, "jooble": joo, "arbeitnow": arb}[which])

        monkeypatch.setattr(requests, "get", fake_http)
        monkeypatch.setattr(requests, "post", fake_http)
        try:
            if which == "adzuna":
                jobs = adzuna.search(text(r), text(r), 10)
            elif which == "jooble":
                jobs = jooble.search(text(r), text(r), 10)
            else:
                query, loc = text(r), r.choice(["", "berlin", "Loc"])
                jobs = arbeitnow.search(query, loc)
                words = [w for w in query.lower().split() if len(w) > 2]
                for job in jobs:
                    assert isinstance(job, Job), label
        except RuntimeError as e:
            for secret in secrets:
                assert secret not in str(e), f"{label}: secret leaked in error {e}"
            continue
        # any other exception type escapes the try and fails the test
        assert isinstance(jobs, list) and all(isinstance(j, Job) for j in jobs), label
        for j in jobs:
            for key in STR_KEYS:
                assert isinstance(getattr(j, key), str), label
        if which == "jooble":
            assert len(jobs) <= 10, label


# ================================================================ PHASE 6: MCP search tool

def _job(r, source):
    return __import__("mcp_server.models", fromlist=["Job"]).Job(
        title=r.choice(["A", "B", "a ", "C"]), company=r.choice(["X", "x", "Y"]), location=r.choice(["L", "l", ""]),
        source=source, source_id=r.choice(["", "1", "2", "3"]),
    )


def test_phase6_mcp_search_tool(monkeypatch):
    from mcp_server import server
    from mcp_server.dedupe import remove_duplicates

    r = rng(6)
    for i in range(N):
        behaviours = {}
        for name in ("adzuna", "jooble", "arbeitnow"):
            roll = r.random()
            if roll < 0.15:
                behaviours[name] = RuntimeError(f"{name} down")
            elif roll < 0.25:
                behaviours[name] = r.choice([ValueError("bad json"), TypeError("null field"), KeyError("x"), AttributeError("none")])
            else:
                behaviours[name] = [_job(r, name) for _ in range(r.randint(0, 25))]

        def make(name):
            def fn(query, location, limit):
                if isinstance(behaviours[name], Exception):
                    raise behaviours[name]
                return list(behaviours[name])
            return fn

        monkeypatch.setattr(server, "SOURCES", {n: make(n) for n in behaviours})
        limit = r.randint(1, 50)
        label = f"phase6 case {i}: " + str({k: (type(v).__name__ if isinstance(v, Exception) else len(v)) for k, v in behaviours.items()})

        result = server.search_jobs("python dev", "", limit)
        assert result.count == len(result.jobs) <= limit, label
        assert set(result.errors) == {n for n, v in behaviours.items() if isinstance(v, Exception)}, label
        for message in result.errors.values():
            assert "null field" not in message and "bad json" not in message, f"{label}: raw exception text leaked"
        assert remove_duplicates(result.jobs) == result.jobs, f"{label}: duplicates"
        ok_sources = {n for n, v in behaviours.items() if not isinstance(v, Exception) and v}
        assert {j.source for j in result.jobs} <= ok_sources, label
        # exact oracle: healthy sources alternate, duplicates drop, then the limit applies
        healthy = {n: list(v) for n, v in behaviours.items() if not isinstance(v, Exception)}
        expected = remove_duplicates(server._interleave(healthy))[:limit]
        assert result.jobs == expected, f"{label}: merged list differs from the oracle"

    # argument validation
    for bad in [("", 5), ("   ", 5), ("ok", 0), ("ok", 51), ("ok", -1)]:
        with pytest.raises(ValueError):
            server.search_jobs(*bad[:1], "", bad[1])
    with pytest.raises(ValueError):
        server.search_jobs_by_source("nonsense", "q", "", 5)


# ================================================================ PHASE 7: matching

def _profile(r):
    from app.models.profile import CandidateProfile, ProjectEntry
    skills = [text(r) for _ in range(r.randint(0, 12))]
    return CandidateProfile(
        name=text(r), skills=skills, education=[text(r) for _ in range(r.randint(0, 3))],
        projects=[ProjectEntry(name=text(r) or "p", description=text(r)) for _ in range(r.randint(0, 4))],
        total_experience_years=r.choice([0, 0.5, 1, 2.5, 5, 8, 15]),
        target_roles=[text(r) for _ in range(r.randint(0, 3))], job_titles=[text(r) for _ in range(r.randint(0, 2))],
    )


def _analysed_job(r):
    skills = [text(r) for _ in range(r.randint(0, 10))]
    job = {"title": text(r), "company": text(r), "description": text(r) + " " + r.choice(
        ["", "3-5 years", "5+ years", "fresher", "Minimum 2 years"]),
        "role": text(r), "education_requirement": r.choice(["Unknown", "Bachelor's in CS", "", "Master", "PhD"])}
    roll = r.random()
    if roll < 0.35:
        job["required_skills"] = skills
        job["preferred_skills"] = [text(r) for _ in range(r.randint(0, 3))]
    elif roll < 0.5:
        job["skills_required"] = skills
    elif roll < 0.7:
        job["required_skills"] = []
        job["preferred_skills"] = []
    return job


def test_phase7_matching_and_ranking(monkeypatch):
    from app.agents.matching_agent import MIN_MATCH_SCORE, rank_jobs_for_candidate
    from app.services import matcher

    r = rng(7)
    monkeypatch.setattr(matcher, "compute_semantic_similarity", lambda a, b: r.random())

    for i in range(N):
        cand = [text(r) for _ in range(r.randint(0, 10))]
        req = [text(r) for _ in range(r.randint(0, 10))]
        pref = [text(r) for _ in range(r.randint(0, 4))]
        label = f"phase7 case {i}: cand={cand} req={req} pref={pref}"

        res = matcher.match_skills(cand, req, pref)
        assert 0.0 <= res["skill_match_score"] <= 1.0, label
        job_side = set(req) | set(pref)
        assert set(res["matched_skills"]) <= job_side, label
        assert set(res["missing_skills"]) <= set(req), label
        # blank skills must never count as a match for anything
        blank_only = matcher.match_skills(["", "   "], [s for s in req if s.strip()] or ["Python"])
        assert blank_only["matched_skills"] == [], f"{label}: blank candidate skill matched something"
        assert matcher.match_skills(cand, ["", "  "])["matched_skills"] == [], f"{label}: blank job skill matched"
        # case-insensitive and exact skills always match
        exact = [s for s in cand if s.strip()]
        if exact:
            assert matcher.match_skills(exact, [exact[0].upper()])["skill_match_score"] == 1.0, label
        # known false-positive pairs
        assert matcher.match_skills(["Java"], ["JavaScript"])["matched_skills"] == [], "Java must not match JavaScript"
        assert matcher.match_skills(["R"], ["React", "Docker", "Terraform"])["matched_skills"] == [], "R must not match R-containing words"
        assert matcher.match_skills(["C"], ["C++", "C#"])["matched_skills"] == [], "C must not match C++/C#"

        body = " ".join(text(r) for _ in range(5))
        for skill in matcher.find_skills_in_text(cand, body):
            assert skill.strip().lower() in body.lower(), label

        profile, job = _profile(r), _analysed_job(r)
        out = matcher.calculate_match_score(profile, job)
        assert isinstance(out["match_score"], int) and 0 <= out["match_score"] <= 100, f"{label}: {out}"
        assert isinstance(out["skills_listed"], bool), label

    for i in range(100):
        profile = _profile(r)
        jobs = [_analysed_job(r) for _ in range(r.randint(0, 30))]
        ranked = rank_jobs_for_candidate(profile, jobs)
        scores = [j["match_score"] for j in ranked]
        assert scores == sorted(scores, reverse=True), f"phase7 rank {i}"
        assert all(s >= MIN_MATCH_SCORE for s in scores)
        assert not any(j["skills_listed"] and not j["matched_skills"] for j in ranked)
        assert len(ranked) <= len(jobs)


# ================================================================ PHASE 8: friendly errors

def test_phase8_friendly_error_messages():
    from app.services.error_messages import friendly_agent_error

    r = rng(8)

    class Weird(Exception):
        def __str__(self):
            return r.choice(["", "x" * 5000, "{'error': {'message': 'secret gsk_ABCDEF'}}"])

    limit_text = ("Error code: 429 - {'error': {'message': 'Rate limit reached for model `m` in organization `org_x` "
                  "on tokens per day (TPD): Limit 200000, Used 199154, Requested 2493. Please try again in %s'}}")
    samples = [limit_text % "11m51.5s", limit_text % "30s", "Error code: 401 invalid_api_key gsk_SECRET", "did not call a tool",
               "tool_use_failed", "timed out", "Connection reset", "", "request id req_4291abc", "tokens 4019"]
    for i in range(N):
        roll = r.random()
        if roll < 0.3:
            err = Weird()
        elif roll < 0.6:
            err = Exception(r.choice(samples) + text(r))
        else:
            err = RuntimeError("".join(r.choice(string.printable) for _ in range(r.randint(0, 300))))
        label = f"phase8 case {i}: {str(err)[:80]!r}"
        out = friendly_agent_error(err)
        assert isinstance(out, str) and 0 < len(out) < 400, label
        for leak in ("gsk_", "org_", "{", "Traceback"):
            assert leak not in out, f"{label}: leaked {leak!r} in {out!r}"
    assert "usage limit" in friendly_agent_error(Exception(limit_text % "11m51.5s"))
    assert "12 minute" in friendly_agent_error(Exception(limit_text % "11m51.5s"))
    assert "4291" and "usage limit" not in friendly_agent_error(Exception("request id req_4291abc"))
    assert "usage limit" not in friendly_agent_error(Exception("tokens 4019"))


# ================================================================ PHASE 9: supervisor

def test_phase9_supervisor_routing():
    from app.agents.supervisor_agent import supervisor_node

    r = rng(9)
    order = ["resume_analyzer", "job_search", "job_analysis", "matching", "recommendation"]
    fields = {"resume_analyzer": "candidate_profile", "job_search": "jobs", "job_analysis": "analyzed_jobs",
              "matching": "ranked_jobs", "recommendation": "recommendations"}
    for i in range(N):
        state = {"candidate_profile": None, "jobs": None, "analyzed_jobs": None, "ranked_jobs": None,
                 "recommendations": None, "errors": [], "current_agent": ""}
        visited, failed_at = [], None
        for step in range(12):
            nxt = supervisor_node(state)["current_agent"]
            assert nxt in order + ["end"], f"phase9 case {i}: invalid route {nxt}"
            if nxt == "end":
                break
            visited.append(nxt)
            if r.random() < 0.12:
                state["errors"] = [f"{nxt} failed"]
                failed_at = nxt
            else:
                state[fields[nxt]] = r.choice([[], ["x"], {"a": 1}, 0]) if nxt != "resume_analyzer" else object()
        else:
            pytest.fail(f"phase9 case {i}: supervisor never terminated: {visited}")
        label = f"phase9 case {i}: {visited} failed_at={failed_at}"
        assert visited == order[: len(visited)], label  # strict stage order, no repeats
        if failed_at:
            assert visited[-1] == failed_at, label     # stops right at the failing stage
        else:
            assert visited == order, label             # empty results still count as done


# ================================================================ PHASE 10: Flask API

@pytest.fixture
def api(monkeypatch, tmp_path):
    from app import main
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(main, "UPLOAD_FOLDER", str(uploads))
    main.app.config["TESTING"] = True
    main._jobs.clear()
    return main, main.app.test_client(), uploads


FILENAMES = ["resume.pdf", "resume.docx", "RESUME.PDF", "../../evil.pdf", "..\\..\\evil.docx", "/abs/evil.pdf", "C:\\evil.pdf",
             "a/b/c.docx", "résumé (1).pdf", "x" * 300 + ".pdf", ".pdf", "pdf", "file.pdf.exe", "file.txt", "", "my resume.final.v2.pdf",
             "日本語.docx", "evil.pdf\x00.exe", "con.pdf", "..", "   .pdf"]


def test_phase10_flask_api(api, monkeypatch, tmp_path):
    main, client, uploads = api
    r = rng(10)
    real_text = "Jane Doe Software Engineer " + "built backend services in Python and SQL " * 5

    seen_paths = []

    def fake_extract(path):
        seen_paths.append(path)
        assert os.path.commonpath([os.path.abspath(path), str(uploads)]) == str(uploads), f"saved outside uploads: {path}"
        roll = r.random()
        if roll < 0.15:
            return {"success": False, "error": "Could not read file: boom"}
        if roll < 0.3:
            return {"success": True, "text": "too short"}
        return {"success": True, "text": real_text}

    monkeypatch.setattr(main, "extract_resume_text", fake_extract)
    monkeypatch.setattr(main, "_analyze_resume_text", lambda t: ({"status": "ok", "recommendations": []}, 200))

    def files_outside_uploads():
        return [p for p in tmp_path.rglob("*") if p.is_file() and uploads not in p.parents]

    started = []
    for i in range(N):
        kind = r.choice(["upload", "start", "start", "status", "nofile", "emptyname"])
        fname = r.choice(FILENAMES)
        label = f"phase10 case {i} {kind} {fname!r}"
        content = os.urandom(r.randint(0, 300))
        if kind in ("upload", "start"):
            resp = client.post(f"/api/resume/{kind}", data={"resume": (io.BytesIO(content), fname)}, content_type="multipart/form-data")
            ext_ok = fname.rsplit(".", 1)[-1].lower() in ("pdf", "docx") if "." in fname else False
            assert resp.status_code < 500, f"{label}: server error {resp.status_code}"
            assert resp.is_json, f"{label}: non-JSON reply"
            if not ext_ok:
                assert resp.status_code == 400, label
            if kind == "start" and resp.status_code == 202:
                started.append(resp.get_json()["job_id"])
        elif kind == "nofile":
            resp = client.post(f"/api/resume/{r.choice(['upload', 'start'])}", data={})
            assert resp.status_code == 400 and resp.is_json, label
        elif kind == "emptyname":
            resp = client.post("/api/resume/start", data={"resume": (io.BytesIO(b"x"), "")}, content_type="multipart/form-data")
            assert resp.status_code == 400, label
        else:
            junk_id = "".join(r.choice(string.ascii_letters + string.digits + "-_%.") for _ in range(r.randint(1, 40)))
            resp = client.get(f"/api/resume/status/{junk_id}")
            assert resp.status_code == 404 and resp.is_json, label
        assert not files_outside_uploads(), f"{label}: wrote a file outside uploads"
        assert not list(uploads.iterdir()), f"{label}: uploaded resume was left on disk"

    assert started, "no job was ever started"
    assert len(started) == len(set(started)), "duplicate job ids"
    deadline = time.time() + 30
    for job_id in started:
        while True:
            body = client.get(f"/api/resume/status/{job_id}").get_json()
            if body["status"] == "done":
                assert body["http_status"] == 200
                break
            assert time.time() < deadline, "job never finished"
            time.sleep(0.005)

    # oversize uploads are refused with JSON, not an HTML error page
    big = client.post("/api/resume/start", data={"resume": (io.BytesIO(b"0" * (21 * 1024 * 1024)), "big.pdf")},
                      content_type="multipart/form-data")
    assert big.status_code == 413 and big.is_json and "large" in big.get_json()["error"].lower()


def test_phase10_job_results_and_expiry(api, monkeypatch):
    main, client, uploads = api
    r = rng("10b")
    monkeypatch.setattr(main, "extract_resume_text", lambda p: {"success": True, "text": "word " * 40})
    outcomes = {}

    def fake_analyze(text_):
        n = len(outcomes)
        roll = r.random()
        if roll < 0.1:
            raise RuntimeError("graph exploded")
        status = r.choice([200, 200, 502, 500])
        outcomes[threading.get_ident(), n] = status
        return ({"status": "ok"} if status == 200 else {"error": "agent failed"}), status

    monkeypatch.setattr(main, "_analyze_resume_text", fake_analyze)
    ids = []
    for _ in range(N):
        resp = client.post("/api/resume/start", data={"resume": (io.BytesIO(b"x"), "r.pdf")}, content_type="multipart/form-data")
        assert resp.status_code == 202
        ids.append(resp.get_json()["job_id"])
    deadline = time.time() + 30
    for job_id in ids:
        while True:
            body = client.get(f"/api/resume/status/{job_id}").get_json()
            if body["status"] == "done":
                assert body["http_status"] in (200, 502, 500)
                assert ("error" in body["result"]) == (body["http_status"] != 200)
                break
            assert time.time() < deadline
            time.sleep(0.005)
    monkeypatch.setattr(main, "JOB_TTL_SECONDS", -1)
    client.post("/api/resume/start", data={"resume": (io.BytesIO(b"x"), "r.pdf")}, content_type="multipart/form-data")
    assert client.get(f"/api/resume/status/{ids[0]}").status_code == 404, "expired job should be pruned"


# ================================================================ PHASE 11: MCP auth

def test_phase11_mcp_bearer_auth():
    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient
    from mcp_server.http_app import BearerTokenMiddleware

    token = "correct-horse-battery-staple"
    app = Starlette(routes=[Route("/mcp", lambda req: PlainTextResponse("secret"), methods=["GET", "POST"]),
                            Route("/health", lambda req: PlainTextResponse("ok")),
                            Route("/other", lambda req: PlainTextResponse("other"))])
    app.add_middleware(BearerTokenMiddleware, token=token)
    client = TestClient(app)
    r = rng(11)
    printable = [c for c in string.printable if c not in "\r\n\x0b\x0c"]
    for i in range(N):
        roll = r.random()
        if roll < 0.15:
            header, ok = f"Bearer {token}", True
        elif roll < 0.2:
            header, ok = f"bearer {token}", True
        elif roll < 0.25:
            header, ok = f"BEARER {token}", True
        elif roll < 0.35:
            header, ok = None, False
        elif roll < 0.45:
            header, ok = f"Bearer {token} ", False
        elif roll < 0.55:
            header, ok = f"Bearer  {token}", False
        elif roll < 0.65:
            header, ok = token, False
        elif roll < 0.75:
            header, ok = f"Basic {token}", False
        elif roll < 0.85:
            cut = r.randint(0, len(token) - 1)
            header, ok = f"Bearer {token[:cut]}", False
        else:
            header, ok = "".join(r.choice(printable) for _ in range(r.randint(0, 60))), False
            if header == f"Bearer {token}":
                ok = True
        path = r.choice(["/mcp", "/mcp", "/other"])
        headers = {} if header is None else {"Authorization": header}
        resp = client.get(path, headers=headers)
        label = f"phase11 case {i}: {path} {header!r}"
        assert resp.status_code == (200 if ok else 401), label
        if not ok:
            assert "secret" not in resp.text and token not in resp.text, label
            assert resp.headers.get("www-authenticate") == "Bearer", label
        assert client.get("/health", headers=headers).status_code == 200, f"{label}: health must stay open"


# ================================================================ PHASE 12: MCP client helpers

def test_phase12_mcp_client_helpers(monkeypatch):
    import requests
    from app.services import mcp_job_client as client

    r = rng(12)
    schemes = ["https://", "http://", "HTTPS://", " https://"]
    hosts = ["x.onrender.com", "hire-path-ai-mcp.onrender.com", "localhost:8000", "a.b.c.d"]
    tails = ["", "/", "/mcp", "/mcp/", "//", "/health", "/mcp/mcp"]
    for i in range(N):
        base = r.choice(schemes) + r.choice(hosts) + r.choice(tails)
        token = r.choice(["", "  ", "tok-123", "  tok-123  "])
        monkeypatch.setenv("MCP_SERVER_URL", base)
        monkeypatch.setenv("MCP_AUTH_TOKEN", token)
        label = f"phase12 case {i}: {base!r} token={token!r}"
        if not token.strip():
            with pytest.raises(RuntimeError) as exc:
                client._remote_server()
            assert "MCP_AUTH_TOKEN" in str(exc.value), label
            continue
        url, headers = client._remote_server()
        assert url.endswith("/mcp") and not url.endswith("/mcp/mcp") or base.rstrip("/").endswith("/mcp/mcp"), f"{label}: {url}"
        assert "://" in url and url.count("://") == 1, label
        assert headers == {"Authorization": f"Bearer {token.strip()}"}, label

    # wake-up: mocked clock and network, random responses
    for i in range(N):
        monkeypatch.setenv("MCP_SERVER_URL", "https://x.onrender.com/mcp")
        clock = {"t": 0.0}
        monkeypatch.setattr(client.time, "monotonic", lambda: clock["t"])
        sleeps = []
        monkeypatch.setattr(client.time, "sleep", lambda s: (sleeps.append(s), clock.__setitem__("t", clock["t"] + s)))
        up_after = r.choice([0, 1, 3, 10, 50, 10_000])
        calls = {"n": 0}

        def fake_get(url, timeout):
            calls["n"] += 1
            assert url == "https://x.onrender.com/health", url
            clock["t"] += r.choice([0.1, 1, 5])
            roll = r.random()
            if roll < 0.2:
                raise requests.exceptions.ConnectionError("down")
            if roll < 0.3:
                raise requests.exceptions.Timeout("slow")
            return SimpleNamespace(status_code=200 if calls["n"] > up_after else r.choice([502, 503, 404]))

        monkeypatch.setattr(client.requests, "get", fake_get)
        timeout = r.choice([5, 30, 75])
        label = f"phase12 wake case {i}: up_after={up_after} timeout={timeout}"
        result = client.wake_remote_server(timeout)
        assert isinstance(result, bool), label
        assert clock["t"] <= timeout + 30, f"{label}: ran far past the timeout ({clock['t']}s)"
        assert calls["n"] <= timeout / client.WAKE_POLL_SECONDS + 2, f"{label}: polled too often"
        if result:
            assert calls["n"] > up_after, label

    monkeypatch.delenv("MCP_SERVER_URL")
    assert client.wake_remote_server() is False

    # root-cause extraction
    for i in range(N):
        err = ValueError(text(r))
        for _ in range(r.randint(0, 4)):
            err = BaseExceptionGroup("group", [err, RuntimeError("sibling")][: r.randint(1, 2)]) if r.random() < 0.8 else err
        out = client._root_cause(err)
        assert isinstance(out, str) and len(out) <= 200, f"phase12 root cause {i}"


# ================================================================ PHASE 13: job-search agent

def test_phase13_job_search_agent(monkeypatch):
    from app.agents import job_search_agent as agent
    from app.models.profile import CandidateProfile

    r = rng(13)
    for i in range(N):
        queries = [text(r) or "q" for _ in range(r.randint(0, 5))]
        monkeypatch.setattr(agent, "generate_search_queries", lambda profile, q=queries: list(q))
        mode = r.choice(["mcp", "direct"])
        monkeypatch.setenv("JOB_SEARCH_MODE", mode)
        mcp_fails = r.random() < 0.4

        def fake_batch(qs, location=""):
            if mcp_fails:
                raise RuntimeError("502 Bad Gateway")
            return [{"source": "all", "count": 1, "errors": {"jooble": "down"} if r.random() < 0.3 else {},
                     "jobs": [{"title": "T", "company": "C", "source": "Adzuna"} for _ in range(r.randint(0, 3))]} for _ in qs]

        monkeypatch.setattr(agent, "search_jobs_batch_via_mcp", fake_batch)

        def fake_direct(*args, **kwargs):
            if r.random() < 0.5:
                return {"success": False, "error": "credentials missing"}
            return {"success": True, "jobs": [{"title": "D", "id": "1"} for _ in range(r.randint(0, 3))]}

        for name in ("search_adzuna_jobs", "search_jooble_jobs", "search_arbeitnow_jobs"):
            monkeypatch.setattr(agent, name, fake_direct)
        monkeypatch.setattr(agent, "search_jobs_via_mcp", lambda q, location="": {"source": "all", "count": 0, "errors": {}, "jobs": []})

        label = f"phase13 case {i}: mode={mode} mcp_fails={mcp_fails} queries={queries}"
        out = agent.search_jobs_for_candidate(CandidateProfile())
        # search_via_reason appears only when MCP failed and the direct APIs were used instead
        assert set(out) - {"search_via_reason"} == {"search_queries", "jobs", "search_via"}, label
        assert ("search_via_reason" in out) == (out["search_via"] == "direct" and mode == "mcp" and bool(queries)), label
        assert out["search_via"] in ("mcp", "direct"), label
        assert out["search_queries"] == queries, label
        assert isinstance(out["jobs"], list), label
        if mode == "mcp" and queries and not mcp_fails:
            assert out["search_via"] == "mcp", label
            assert all(j["experience_required"] == "Unknown" and j["skills_required"] == [] for j in out["jobs"]), label
        if mode == "mcp" and queries and mcp_fails:
            assert out["search_via"] == "direct", f"{label}: fallback not reported"
        if mode == "direct":
            assert out["search_via"] == "direct", label


# ================================================================ PHASE 14: whole pipeline

def test_phase14_full_pipeline_with_random_failures(monkeypatch):
    from app import main
    from app.graph import workflow as wf
    from app.services import matcher

    r = rng(14)
    monkeypatch.setattr(matcher, "compute_semantic_similarity", lambda a, b: r.random())
    limit_error = RuntimeError("Error code: 429 - rate_limit_exceeded tokens per day (TPD) Please try again in 11m51s")

    for i in range(N):
        plan = {"resume": r.random(), "search": r.random(), "analysis": r.random(), "rec": r.random()}
        n_jobs = r.choice([0, 1, 5, 15, 30])

        def analyze_resume(text_):
            if plan["resume"] < 0.1:
                raise r.choice([RuntimeError("could not parse"), limit_error])
            return _profile(r)

        def search(profile, **kw):
            if plan["search"] < 0.08:
                raise RuntimeError("search exploded")
            jobs = []
            for k in range(n_jobs):
                j = {"title": f"Job {k}", "company": f"Co{k % 4}", "location": "Remote", "description": text(r) + " 3-5 years",
                     "url": "https://x", "source": r.choice(["Adzuna", "Jooble", "Arbeitnow"]), "source_id": str(k)}
                jobs.append(j)
            return {"search_queries": ["q1", "q2"], "jobs": jobs, "search_via": r.choice(["mcp", "direct"])}

        def analyze_jobs(jobs):
            mode = plan["analysis"]
            out = []
            for j in jobs:
                j = dict(j)
                if mode < 0.15 or r.random() < 0.1:
                    j["analysis_error"] = "Job Analysis Agent failed: rate_limit_exceeded 429"
                else:
                    j["required_skills"] = [text(r) for _ in range(r.randint(0, 6))]
                    j["preferred_skills"] = []
                    j["skills_required"] = j["required_skills"]
                    j["education_requirement"] = "Unknown"
                    j["role"] = "Engineer"
                out.append(j)
            return out

        def recommendations(profile, ranked):
            if plan["rec"] < 0.08:
                raise RuntimeError("recommendation exploded")
            out = []
            for j in ranked[:10]:
                j["why_it_matches"] = "ok"
                out.append(j)
            return out

        monkeypatch.setattr(wf, "analyze_resume", analyze_resume)
        monkeypatch.setattr(wf, "search_jobs_for_candidate", search)
        monkeypatch.setattr(wf, "analyze_jobs", analyze_jobs)
        monkeypatch.setattr(wf, "generate_recommendations", recommendations)

        label = f"phase14 case {i}: plan={plan} jobs={n_jobs}"
        body, status = main._analyze_resume_text("resume text " * 30)
        assert status in (200, 502), f"{label}: unexpected status {status} {body}"
        if status == 502:
            assert isinstance(body["error"], str) and body["error"] and "{" not in body["error"], f"{label}: {body}"
            continue
        for key in ("status", "candidate_profile", "search_queries", "search_via", "recommendations", "token_usage"):
            assert key in body, f"{label}: missing {key}"
        recs = body["recommendations"]
        scores = [x["match_score"] for x in recs]
        assert len(recs) <= 10 and scores == sorted(scores, reverse=True), label
        assert all(isinstance(s, int) and 40 <= s <= 100 for s in scores), f"{label}: {scores}"
        assert not any(x["skills_listed"] and not x["matched_skills"] for x in recs), label
        assert body["search_via"] in ("mcp", "direct"), label
        if n_jobs and plan["analysis"] < 0.15 and plan["resume"] >= 0.1 and plan["search"] >= 0.08:
            pytest.fail(f"{label}: every job failed analysis yet the run reported success")
