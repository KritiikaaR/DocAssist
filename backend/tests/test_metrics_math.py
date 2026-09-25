"""percentile()/summarize() rollup math and the pricing table, independent of tracing."""
import pytest

from observability.eval import groundedness
from observability.metrics import percentile, summarize
from observability.pricing import cost_usd


# ---- percentile -------------------------------------------------------------
def test_percentile_nearest_rank():
    values = list(range(1, 101))
    assert percentile(values, 50) == 50
    assert percentile(values, 95) == 95


def test_percentile_empty_is_zero():
    assert percentile([], 95) == 0.0


def test_percentile_single_value():
    assert percentile([42.0], 50) == 42.0
    assert percentile([42.0], 95) == 42.0


# ---- pricing ------------------------------------------------------------------
def test_cost_matches_versioned_model_name():
    # 1M input tokens of gpt-4o = $2.50
    assert cost_usd("gpt-4o-2024-08-06", 1_000_000, 0) == pytest.approx(2.50)


def test_cost_includes_output_tokens():
    assert cost_usd("gpt-4o", 0, 1_000_000) == pytest.approx(10.00)


def test_cost_unknown_model_is_zero():
    assert cost_usd("some-new-model", 1000, 1000) == 0.0
    assert cost_usd(None, 1000, 1000) == 0.0


# ---- groundedness -------------------------------------------------------------
def test_groundedness_fully_supported():
    assert groundedness("Jaeger receives spans", ["Jaeger receives spans over OTLP"]) == 1.0


def test_groundedness_unsupported():
    assert groundedness("bananas mangoes pineapples", ["Jaeger receives spans"]) == 0.0


def test_groundedness_empty_answer():
    assert groundedness("", ["anything"]) == 0.0


# ---- summarize ------------------------------------------------------------------
def _row(ms, status="ok", ttft=None, steps=None, cost=0.001, g=0.8, tokens=(100, 20)):
    return {
        "total_ms": ms, "status": status, "ttft_ms": ttft, "cost_usd": cost, "groundedness": g,
        "input_tokens": tokens[0], "output_tokens": tokens[1],
        "steps": steps or [{"name": "retrieve", "ms": 10}, {"name": "generate", "ms": 30}],
    }


def test_summarize_empty():
    assert summarize([])["count"] == 0


def test_summarize_rollup():
    rows = [_row(100, ttft=20), _row(200, status="error", ttft=40), _row(300, ttft=60)]
    s = summarize(rows)
    assert s["count"] == 3
    assert s["error_rate"] == pytest.approx(0.333, abs=1e-3)
    assert s["p50_ms"] == 200
    assert s["ttft_p50_ms"] == 40
    assert s["step_share"] == {"retrieve": 0.25, "generate": 0.75}
    assert s["avg_tokens"] == 120


def test_summarize_ignores_null_ttft_for_quiz_rows():
    """Quiz requests don't stream, so they never get a ttft_ms — the percentile
    should be computed only from the rows that have one."""
    rows = [_row(100, ttft=None), _row(200, ttft=50)]
    s = summarize(rows)
    assert s["ttft_p50_ms"] == 50


def test_summarize_null_groundedness_excluded_from_average():
    rows = [_row(100, g=None), _row(200, g=1.0)]
    assert summarize(rows)["avg_groundedness"] == 1.0
