"""Aggregate stats for the dashboard, computed from the request rows."""
from statistics import mean


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile. p is 0-100."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, round(p / 100 * len(ordered)))
    return ordered[min(rank, len(ordered)) - 1]


def summarize(rows: list[dict]) -> dict:
    if not rows:
        return {
            "count": 0, "error_rate": 0.0, "p50_ms": 0.0, "p95_ms": 0.0,
            "ttft_p50_ms": 0.0, "ttft_p95_ms": 0.0,
            "avg_cost_usd": 0.0, "total_cost_usd": 0.0, "avg_tokens": 0.0,
            "avg_groundedness": None, "step_avg_ms": {}, "step_share": {},
        }

    totals = [r["total_ms"] for r in rows]
    costs = [r["cost_usd"] for r in rows]
    # Only chat requests stream, so only they have a TTFT — quiz rows leave it null.
    ttfts = [r["ttft_ms"] for r in rows if r.get("ttft_ms") is not None]

    step_times: dict[str, list[float]] = {}
    for r in rows:
        for s in r["steps"]:
            step_times.setdefault(s["name"], []).append(s["ms"])
    step_avg = {k: round(mean(v), 2) for k, v in step_times.items()}
    step_sum = sum(step_avg.values()) or 1
    step_share = {k: round(v / step_sum, 3) for k, v in step_avg.items()}

    scored = [r["groundedness"] for r in rows if r["groundedness"] is not None]
    return {
        "count": len(rows),
        "error_rate": round(sum(r["status"] == "error" for r in rows) / len(rows), 3),
        "p50_ms": round(percentile(totals, 50), 2),
        "p95_ms": round(percentile(totals, 95), 2),
        "ttft_p50_ms": round(percentile(ttfts, 50), 2),
        "ttft_p95_ms": round(percentile(ttfts, 95), 2),
        "avg_cost_usd": round(mean(costs), 8),
        "total_cost_usd": round(sum(costs), 8),
        "avg_tokens": round(mean(r["input_tokens"] + r["output_tokens"] for r in rows), 1),
        "avg_groundedness": round(mean(scored), 3) if scored else None,
        "step_avg_ms": step_avg,
        "step_share": step_share,
    }
