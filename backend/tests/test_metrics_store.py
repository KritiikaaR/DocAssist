"""RequestStore: add/recent/clear round-trip against a real (temp-path) SQLite file."""
from observability.store import RequestStore


def _row(trace_id="abc123", **overrides):
    row = {
        "trace_id": trace_id,
        "created_at": 1_700_000_000.0,
        "kind": "chat",
        "question": "What is DocAssist?",
        "status": "ok",
        "error": None,
        "total_ms": 842.5,
        "ttft_ms": 210.3,
        "steps": [{"name": "retrieve", "ms": 12.0}, {"name": "generate", "ms": 800.0}],
        "model": "gpt-4o",
        "input_tokens": 500,
        "output_tokens": 120,
        "cost_usd": 0.00263,
        "groundedness": 0.82,
    }
    row.update(overrides)
    return row


def test_add_and_recent_round_trip(tmp_path):
    store = RequestStore(tmp_path / "metrics.db")
    store.add(_row())

    rows = store.recent()
    assert len(rows) == 1
    row = rows[0]
    assert row["trace_id"] == "abc123"
    assert row["question"] == "What is DocAssist?"
    assert row["steps"] == [{"name": "retrieve", "ms": 12.0}, {"name": "generate", "ms": 800.0}]
    assert row["ttft_ms"] == 210.3
    assert row["cost_usd"] == 0.00263


def test_quiz_row_has_no_ttft(tmp_path):
    store = RequestStore(tmp_path / "metrics.db")
    store.add(_row(trace_id="quiz1", kind="quiz", ttft_ms=None))

    row = store.recent()[0]
    assert row["kind"] == "quiz"
    assert row["ttft_ms"] is None


def test_recent_orders_newest_first(tmp_path):
    store = RequestStore(tmp_path / "metrics.db")
    store.add(_row(trace_id="older", created_at=1_700_000_000.0))
    store.add(_row(trace_id="newer", created_at=1_700_000_100.0))

    rows = store.recent()
    assert [r["trace_id"] for r in rows] == ["newer", "older"]


def test_recent_respects_limit(tmp_path):
    store = RequestStore(tmp_path / "metrics.db")
    for i in range(5):
        store.add(_row(trace_id=f"t{i}", created_at=1_700_000_000.0 + i))

    assert len(store.recent(limit=2)) == 2


def test_clear_empties_the_table(tmp_path):
    store = RequestStore(tmp_path / "metrics.db")
    store.add(_row())
    assert len(store.recent()) == 1

    store.clear()
    assert store.recent() == []


def test_add_is_upsert_on_trace_id(tmp_path):
    """A retried on_end for the same trace (shouldn't happen, but the schema
    guards it) overwrites rather than duplicating the row."""
    store = RequestStore(tmp_path / "metrics.db")
    store.add(_row(status="error"))
    store.add(_row(status="ok"))

    rows = store.recent()
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"
