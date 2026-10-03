from app.services.error_messages import friendly_agent_error


def test_groq_daily_rate_limit_with_wait_time():
    # The exact shape of error Groq returns when the daily token quota is exhausted.
    error = Exception(
        "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
        "`openai/gpt-oss-20b` in organization `org_01kxb9bdr2e63s33yz6m9pvdbg` "
        "service tier `on_demand` on tokens per day (TPD): Limit 200000, Used "
        "199118, Requested 1914. Please try again in 7m25.823999999s. Need more "
        "tokens? Upgrade to Dev Tier today at https://console.groq.com/settings/billing', "
        "'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
    )
    message = friendly_agent_error(error)
    assert "today's usage limit" in message
    assert "7 minute" in message
    assert "429" not in message
    assert "org_01kxb9bdr2e63s33yz6m9pvdbg" not in message


def test_rate_limit_seconds_only_rounds_up_to_under_a_minute():
    error = Exception("rate_limit_exceeded: try again in 25.5s")
    message = friendly_agent_error(error)
    assert "under a minute" in message


def test_rate_limit_without_extractable_wait_time_still_friendly():
    error = Exception("Rate limit reached, code: rate_limit_exceeded")
    message = friendly_agent_error(error)
    assert "usage limit" in message
    assert "rate_limit_exceeded" not in message


def test_per_minute_rate_limit_says_current_not_todays():
    error = Exception("Rate limit reached on tokens per minute (TPM): rate_limit_exceeded, try again in 3.2s")
    message = friendly_agent_error(error)
    assert "the current usage limit" in message


def test_auth_error():
    error = Exception("Error code: 401 - invalid_api_key: Incorrect API key provided")
    message = friendly_agent_error(error)
    assert "credentials" in message
    assert "401" not in message


def test_token_count_containing_401_is_not_mistaken_for_auth_error():
    # Regression: "401" used to be a bare substring check, so a token count
    # like 14019 (contains "401") was wrongly classified as an auth failure
    # even with valid credentials.
    error = Exception("Requested 14019 tokens exceeds model's context window of 8192")
    message = friendly_agent_error(error)
    assert "credentials" not in message


def test_token_count_containing_429_is_not_mistaken_for_rate_limit():
    error = Exception("Batch processed 4291 tokens successfully")
    message = friendly_agent_error(error)
    assert "usage limit" not in message


def test_standalone_401_is_still_detected_as_auth_error():
    error = Exception("HTTP 401 returned by upstream service")
    message = friendly_agent_error(error)
    assert "credentials" in message


def test_structured_output_parse_failure():
    error = ValueError("Could not parse resume into a profile: Failed to parse response into CandidateProfile")
    message = friendly_agent_error(error)
    assert "reading some details from your resume" in message
    assert "CandidateProfile" not in message


def test_timeout_error():
    error = Exception("Request timed out after 30s")
    message = friendly_agent_error(error)
    assert "too long to respond" in message


def test_network_error():
    error = Exception("Network error calling Adzuna: Connection refused")
    message = friendly_agent_error(error)
    assert "Couldn't reach" in message


def test_unrecognized_error_falls_back_to_generic_message():
    error = Exception("KeyError: 'unexpected_field'")
    message = friendly_agent_error(error)
    assert message == "Something went wrong while processing your request. Please try again in a moment."


def test_model_did_not_call_a_tool_gets_clear_resume_message():
    msg = friendly_agent_error(Exception("Error code: 400 - Tool choice is required, but model did not call a tool (tool_use_failed)"))
    assert "couldn't find resume details" in msg


def test_malformed_tool_call_gets_trouble_reading_message():
    msg = friendly_agent_error(Exception("Error code: 400 - Failed to parse tool call arguments as JSON (tool_use_failed)"))
    assert "trouble reading" in msg
