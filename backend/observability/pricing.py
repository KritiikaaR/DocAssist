"""Turns token counts into dollars.

Prices are USD per 1M tokens. They change — check
https://platform.openai.com/docs/pricing and update this table before quoting
these numbers anywhere that matters (a resume, a design doc).
"""

PRICES = {
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "text-embedding-3-small": {"input": 0.02, "output": 0.0},
    "mock-model": {"input": 0.15, "output": 0.60},
}


def cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    if not model:
        return 0.0
    # Providers often return versioned names like "gpt-4o-2024-08-06".
    match = next((k for k in PRICES if model.startswith(k)), None)
    if match is None:
        return 0.0
    p = PRICES[match]
    return (input_tokens * p["input"] + output_tokens * p["output"]) / 1_000_000
