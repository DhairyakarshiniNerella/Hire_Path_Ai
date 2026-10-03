import pytest
from app.services.groq_client import StructuredLLMWithFallback


class FakeClient:
    """Stands in for one ChatGroq(...).with_structured_output(...) runnable."""

    def __init__(self, behavior):
        self._behavior = behavior
        self.call_count = 0

    def invoke(self, messages):
        self.call_count += 1
        return self._behavior(messages)


def make_client(behavior):
    """behavior: a function(messages) -> result, or one that raises."""
    return FakeClient(behavior)


def test_uses_first_client_when_it_succeeds():
    primary = make_client(lambda messages: {"parsed": "ok"})
    fallback = make_client(lambda messages: {"parsed": "should not be used"})

    llm = StructuredLLMWithFallback([primary, fallback])
    result = llm.invoke(["some message"])

    assert result == {"parsed": "ok"}
    assert primary.call_count == 1
    assert fallback.call_count == 0


def test_falls_back_to_second_client_on_rate_limit_error():
    def primary_behavior(messages):
        raise Exception("Error code: 429 - rate_limit_exceeded: tokens per day limit reached")

    primary = make_client(primary_behavior)
    fallback = make_client(lambda messages: {"parsed": "from fallback key"})

    llm = StructuredLLMWithFallback([primary, fallback])
    result = llm.invoke(["some message"])

    assert result == {"parsed": "from fallback key"}
    assert primary.call_count == 1
    assert fallback.call_count == 1


def test_does_not_fall_back_on_non_rate_limit_error():
    def primary_behavior(messages):
        raise ValueError("Could not parse response into schema")

    primary = make_client(primary_behavior)
    fallback = make_client(lambda messages: {"parsed": "should not be reached"})

    llm = StructuredLLMWithFallback([primary, fallback])

    with pytest.raises(ValueError, match="Could not parse response"):
        llm.invoke(["some message"])

    assert fallback.call_count == 0


def test_raises_original_error_when_all_clients_rate_limited():
    def always_rate_limited(messages):
        raise Exception("rate_limit_exceeded")

    primary = make_client(always_rate_limited)
    fallback = make_client(always_rate_limited)

    llm = StructuredLLMWithFallback([primary, fallback])

    with pytest.raises(Exception, match="rate_limit_exceeded"):
        llm.invoke(["some message"])

    assert primary.call_count == 1
    assert fallback.call_count == 1


def test_single_client_behaves_like_before_no_fallback_configured():
    only_client = make_client(lambda messages: {"parsed": "result"})
    llm = StructuredLLMWithFallback([only_client])
    assert llm.invoke(["msg"]) == {"parsed": "result"}


def test_requires_at_least_one_client():
    with pytest.raises(ValueError):
        StructuredLLMWithFallback([])


# ---------- malformed tool-call retry ----------

MALFORMED = "Error code: 400 - {'error': {'code': 'tool_use_failed', 'message': 'Failed to parse tool call arguments as JSON'}}"


def test_retries_same_client_on_malformed_tool_call_then_succeeds():
    calls = {"n": 0}

    def flaky(messages):
        calls["n"] += 1
        if calls["n"] < 3:
            raise Exception(MALFORMED)
        return {"parsed": "ok"}

    client = make_client(flaky)
    assert StructuredLLMWithFallback([client]).invoke(["m"]) == {"parsed": "ok"}
    assert client.call_count == 3


def test_gives_up_after_max_malformed_attempts():
    from app.services.groq_client import MALFORMED_CALL_ATTEMPTS

    def always(messages):
        raise Exception(MALFORMED)

    client = make_client(always)
    with pytest.raises(Exception, match="tool_use_failed"):
        StructuredLLMWithFallback([client]).invoke(["m"])
    assert client.call_count == MALFORMED_CALL_ATTEMPTS


def test_other_errors_are_not_retried():
    def boom(messages):
        raise Exception("Error code: 500 - server exploded")

    client = make_client(boom)
    with pytest.raises(Exception, match="server exploded"):
        StructuredLLMWithFallback([client]).invoke(["m"])
    assert client.call_count == 1


def test_rate_limit_still_falls_back_after_malformed_retries():
    def primary(messages):
        raise Exception("Error code: 429 - rate_limit_exceeded")

    p = make_client(primary)
    f = make_client(lambda messages: {"parsed": "fallback"})
    assert StructuredLLMWithFallback([p, f]).invoke(["m"]) == {"parsed": "fallback"}
    assert p.call_count == 1  # rate limits are not retried on the same key


def test_retries_brief_connection_error_then_succeeds():
    calls = {"n": 0}

    def blip(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            raise Exception("Connection error.")
        return {"parsed": "ok"}

    client = make_client(blip)
    assert StructuredLLMWithFallback([client]).invoke(["m"]) == {"parsed": "ok"}
    assert client.call_count == 2
