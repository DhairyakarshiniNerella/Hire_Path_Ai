from app.services import token_tracker


class FakeAIMessage:
    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata


def setup_function(_):
    # Every test starts from a clean usage log, since it's module-level state
    token_tracker.reset_usage()


def test_reset_usage_clears_log():
    token_tracker.log_usage("Agent A", FakeAIMessage({"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}))
    token_tracker.reset_usage()
    summary = token_tracker.get_usage_summary()
    assert summary == {"total_tokens": 0, "by_agent": {}, "llm_call_count": 0}


def test_log_usage_records_entry():
    token_tracker.log_usage(
        "Resume Analyzer Agent",
        FakeAIMessage({"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}),
    )
    summary = token_tracker.get_usage_summary()
    assert summary["total_tokens"] == 150
    assert summary["by_agent"]["Resume Analyzer Agent"] == 150
    assert summary["llm_call_count"] == 1


def test_log_usage_missing_usage_metadata_is_ignored():
    message_without_usage = FakeAIMessage(None)
    token_tracker.log_usage("Agent X", message_without_usage)
    summary = token_tracker.get_usage_summary()
    assert summary == {"total_tokens": 0, "by_agent": {}, "llm_call_count": 0}


def test_log_usage_missing_usage_metadata_attribute_entirely():
    class NoUsageAttr:
        pass

    token_tracker.log_usage("Agent X", NoUsageAttr())
    summary = token_tracker.get_usage_summary()
    assert summary["llm_call_count"] == 0


def test_get_usage_summary_aggregates_multiple_calls_same_agent():
    token_tracker.log_usage("Agent A", FakeAIMessage({"input_tokens": 10, "output_tokens": 10, "total_tokens": 20}))
    token_tracker.log_usage("Agent A", FakeAIMessage({"input_tokens": 5, "output_tokens": 5, "total_tokens": 10}))
    summary = token_tracker.get_usage_summary()
    assert summary["by_agent"]["Agent A"] == 30
    assert summary["total_tokens"] == 30
    assert summary["llm_call_count"] == 2


def test_get_usage_summary_aggregates_multiple_agents():
    token_tracker.log_usage("Agent A", FakeAIMessage({"input_tokens": 10, "output_tokens": 0, "total_tokens": 10}))
    token_tracker.log_usage("Agent B", FakeAIMessage({"input_tokens": 20, "output_tokens": 0, "total_tokens": 20}))
    summary = token_tracker.get_usage_summary()
    assert summary["by_agent"] == {"Agent A": 10, "Agent B": 20}
    assert summary["total_tokens"] == 30
    assert summary["llm_call_count"] == 2


def test_log_usage_defaults_missing_token_fields_to_zero():
    # A non-empty usage dict missing individual keys should default those to 0
    # (an empty dict is falsy and short-circuits via the "if not usage" check instead).
    token_tracker.log_usage("Agent A", FakeAIMessage({"total_tokens": 0}))
    summary = token_tracker.get_usage_summary()
    assert summary["by_agent"]["Agent A"] == 0
    assert summary["llm_call_count"] == 1


def test_log_usage_empty_usage_dict_is_treated_as_missing():
    # An empty dict is falsy in Python, so this hits the same short-circuit as None
    token_tracker.log_usage("Agent A", FakeAIMessage({}))
    summary = token_tracker.get_usage_summary()
    assert summary == {"total_tokens": 0, "by_agent": {}, "llm_call_count": 0}
