import os
import re
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()

MODEL_NAME = "openai/gpt-oss-20b"

# GROQ_API_KEY_2 is optional. If it's not set, only the primary key is used
# and behavior is unchanged from before this file existed.
_PRIMARY_KEY = os.getenv("GROQ_API_KEY")
_FALLBACK_KEY = os.getenv("GROQ_API_KEY_2")


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return "rate_limit_exceeded" in text or bool(re.search(r"\b429\b", text))


def _is_malformed_tool_call_error(error: Exception) -> bool:
    # Groq returns 400 tool_use_failed when the model emits broken JSON for the
    # structured-output tool call (e.g. a missing closing bracket). It's a random
    # generation slip, so asking again normally works.
    text = str(error).lower()
    return "tool_use_failed" in text or "failed to parse tool call" in text


def _is_transient_network_error(error: Exception) -> bool:
    # A brief network blip or timeout talking to Groq; the next attempt usually goes through.
    text = str(error).lower()
    return "connection error" in text or "timed out" in text or "timeout" in text


# Total tries per client for transient failures (malformed tool call, brief network blip).
MALFORMED_CALL_ATTEMPTS = 3


class StructuredLLMWithFallback:
    """
    Wraps one or more Groq-backed structured-output clients bound to the
    same Pydantic schema, and tries them in order. Only falls through to
    the next client on a rate-limit error - each key has its own separate
    free-tier daily quota, so a second key can pick up where the first
    one's quota ran out. A malformed tool-call (tool_use_failed) is retried
    on the same client, since it's a random generation slip. Any other kind
    of failure (bad prompt, real outage) raises immediately from the first
    client, since a different key wouldn't fix it.
    """

    def __init__(self, clients: list):
        if not clients:
            raise ValueError("At least one Groq client is required")
        self._clients = clients

    def _invoke_with_retry(self, client, messages):
        for attempt in range(1, MALFORMED_CALL_ATTEMPTS + 1):
            try:
                return client.invoke(messages)
            except Exception as e:
                retryable = _is_malformed_tool_call_error(e) or _is_transient_network_error(e)
                if retryable and attempt < MALFORMED_CALL_ATTEMPTS:
                    continue
                raise

    def invoke(self, messages):
        last_error = None
        for index, client in enumerate(self._clients):
            try:
                return self._invoke_with_retry(client, messages)
            except Exception as e:
                is_last_client = index == len(self._clients) - 1
                if _is_rate_limit_error(e) and not is_last_client:
                    last_error = e
                    continue
                raise
        raise last_error


def build_structured_llm(pydantic_model, temperature: float = 0) -> StructuredLLMWithFallback:
    """
    Builds a structured-output client for the given Pydantic schema, backed
    by GROQ_API_KEY, with GROQ_API_KEY_2 (if set) as an automatic fallback
    when the primary key's daily/per-minute quota is exhausted.
    """
    api_keys = [key for key in (_PRIMARY_KEY, _FALLBACK_KEY) if key]
    clients = [
        ChatGroq(
            model=MODEL_NAME, temperature=temperature, groq_api_key=key,
            reasoning_effort="low", max_tokens=6000,
        ).with_structured_output(
            pydantic_model, include_raw=True
        )
        for key in api_keys
    ]
    return StructuredLLMWithFallback(clients)
