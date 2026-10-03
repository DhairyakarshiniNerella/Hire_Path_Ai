# Tracks how many tokens each Groq LLM call uses during one workflow run.
# Useful for understanding real cost and staying aware of Groq's free-tier
# rate limits (tokens per minute AND tokens per day).

_usage_log = []


def reset_usage():
    """Call this once at the start of a new resume analysis run."""
    _usage_log.clear()


def log_usage(agent_name: str, ai_message):
    """
    Reads token counts off a raw AIMessage (returned when a structured LLM
    call is made with include_raw=True) and records them under the given
    agent's name. Silently does nothing if usage data isn't available.
    """
    usage = getattr(ai_message, "usage_metadata", None)
    if not usage:
        return

    entry = {
        "agent": agent_name,
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 0),
    }
    _usage_log.append(entry)
    # flush=True ensures this appears immediately even when stdout is
    # redirected to a file/pipe rather than an interactive terminal
    # (Python block-buffers print() output in that case by default).
    print(
        f"[tokens] {agent_name}: {entry['total_tokens']} total "
        f"(in: {entry['input_tokens']}, out: {entry['output_tokens']})",
        flush=True,
    )


def get_usage_summary() -> dict:
    """Returns the grand total and a per-agent breakdown for the current run."""
    totals_by_agent = {}
    grand_total = 0

    for entry in _usage_log:
        agent = entry["agent"]
        totals_by_agent[agent] = totals_by_agent.get(agent, 0) + entry["total_tokens"]
        grand_total += entry["total_tokens"]

    return {
        "total_tokens": grand_total,
        "by_agent": totals_by_agent,
        "llm_call_count": len(_usage_log),
    }
