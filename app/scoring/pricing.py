"""Approximate per-token pricing for cost logging.

Anthropic pricing changes over time - these are current as of the
skill/documentation this project was built against. Update here if pricing
changes; nothing else in the codebase should hardcode a rate.
"""

# USD per token (list price / 1,000,000)
_PRICING_PER_TOKEN_USD = {
    "claude-haiku-4-5-20251001": {"input": 1.00 / 1_000_000, "output": 5.00 / 1_000_000},
    "claude-sonnet-5": {"input": 3.00 / 1_000_000, "output": 15.00 / 1_000_000},
}

_CACHE_READ_MULTIPLIER = 0.1
_CACHE_WRITE_MULTIPLIER = 1.25


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float:
    rates = _PRICING_PER_TOKEN_USD.get(model)
    if rates is None:
        return 0.0

    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_read_tokens * rates["input"] * _CACHE_READ_MULTIPLIER
        + cache_creation_tokens * rates["input"] * _CACHE_WRITE_MULTIPLIER
    )
