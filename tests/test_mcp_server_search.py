import time

from mcp_server import server
from mcp_server.models import Job


def fake_source(name, delay=0.0, fail=False):
    def search(query, location, limit):
        time.sleep(delay)
        if fail:
            raise RuntimeError(f"{name} is down")
        return [Job(title=f"{name} job", company=name, source_id=name, source=name)]
    return search


def test_search_jobs_queries_sources_in_parallel(monkeypatch):
    monkeypatch.setattr(server, "SOURCES", {n: fake_source(n, delay=0.5) for n in ("a", "b", "c")})

    start = time.time()
    result = server.search_jobs("python")
    elapsed = time.time() - start

    assert result.count == 3
    assert elapsed < 1.0  # sequential would take about 1.5 seconds


def test_search_jobs_result_order_does_not_depend_on_finish_order(monkeypatch):
    # "a" finishes last, but its job must still come first (SOURCES order).
    monkeypatch.setattr(server, "SOURCES", {
        "a": fake_source("a", delay=0.3),
        "b": fake_source("b"),
        "c": fake_source("c"),
    })

    result = server.search_jobs("python")

    assert [j.company for j in result.jobs] == ["a", "b", "c"]


def test_search_jobs_failed_source_is_reported_and_others_still_return(monkeypatch):
    monkeypatch.setattr(server, "SOURCES", {
        "a": fake_source("a", fail=True),
        "b": fake_source("b"),
        "c": fake_source("c"),
    })

    result = server.search_jobs("python")

    assert result.errors == {"a": "a is down"}
    assert [j.company for j in result.jobs] == ["b", "c"]


def test_search_jobs_all_sources_failing_returns_empty_with_errors(monkeypatch):
    monkeypatch.setattr(server, "SOURCES", {n: fake_source(n, fail=True) for n in ("a", "b")})

    result = server.search_jobs("python")

    assert result.count == 0
    assert set(result.errors) == {"a", "b"}
