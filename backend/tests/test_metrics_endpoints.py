"""GET /metrics/summary, GET /metrics/requests, DELETE /metrics — and the access
control in front of them.

Deliberately does NOT import app.py: app.py builds a real RAGPipeline at import
time (OpenAIEmbeddings/ChatOpenAI, which need an API key). The blueprint only
depends on the store, so it's wired onto a bare Flask app here instead.
"""
from flask import Flask
import pytest

from observability.store import RequestStore
from observability.tracing import metrics_blueprint


_next_created_at = [1_700_000_000.0]


def _row(trace_id, total_ms=500.0, status="ok"):
    _next_created_at[0] += 1
    return {
        "trace_id": trace_id, "created_at": _next_created_at[0], "kind": "chat",
        "question": "q", "status": status, "error": None, "total_ms": total_ms,
        "ttft_ms": 100.0, "steps": [{"name": "generate", "ms": total_ms}],
        "model": "gpt-4o", "input_tokens": 50, "output_tokens": 20,
        "cost_usd": 0.001, "groundedness": 0.9,
    }


def make_client(tmp_path, monkeypatch, token=None):
    if token is not None:
        monkeypatch.setenv("METRICS_ADMIN_TOKEN", token)
    else:
        monkeypatch.delenv("METRICS_ADMIN_TOKEN", raising=False)

    store = RequestStore(tmp_path / "metrics.db")
    app = Flask(__name__)
    app.register_blueprint(metrics_blueprint(store))
    return app.test_client(), store


# ---- no token configured -> local-only -------------------------------------
def test_local_request_allowed_without_token(tmp_path, monkeypatch):
    client, store = make_client(tmp_path, monkeypatch, token=None)
    store.add(_row("t1"))

    resp = client.get("/metrics/summary", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 1


def test_remote_request_blocked_without_token(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, token=None)

    resp = client.get("/metrics/summary", environ_overrides={"REMOTE_ADDR": "203.0.113.5"})
    assert resp.status_code == 403


# ---- token configured --------------------------------------------------------
def test_request_with_correct_header_token_allowed(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, token="secret")

    resp = client.get(
        "/metrics/summary",
        headers={"X-Metrics-Token": "secret"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.5"},
    )
    assert resp.status_code == 200


def test_request_with_correct_query_token_allowed(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, token="secret")

    resp = client.get(
        "/metrics/summary?token=secret", environ_overrides={"REMOTE_ADDR": "203.0.113.5"}
    )
    assert resp.status_code == 200


def test_request_with_wrong_token_rejected(tmp_path, monkeypatch):
    client, _ = make_client(tmp_path, monkeypatch, token="secret")

    resp = client.get(
        "/metrics/summary",
        headers={"X-Metrics-Token": "wrong"},
        environ_overrides={"REMOTE_ADDR": "203.0.113.5"},
    )
    assert resp.status_code == 401


def test_local_request_still_requires_token_once_one_is_set(tmp_path, monkeypatch):
    """Setting a token switches the whole endpoint to token-gated — loopback
    no longer gets a free pass, so a misconfigured deployment can't be reached
    accidentally from the box it runs on either."""
    client, _ = make_client(tmp_path, monkeypatch, token="secret")

    resp = client.get("/metrics/summary", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 401


def test_options_preflight_is_never_blocked(tmp_path, monkeypatch):
    """Sending X-Metrics-Token as a real header makes the browser precede the
    request with a CORS preflight OPTIONS carrying no token. If auth blocked
    that too, every token-authenticated fetch from the dashboard would fail at
    the network level before Flask ever saw a real request — regardless of
    whether a token is configured or the request is remote."""
    client, _ = make_client(tmp_path, monkeypatch, token="secret")

    resp = client.open(
        "/metrics/summary", method="OPTIONS", environ_overrides={"REMOTE_ADDR": "203.0.113.5"}
    )
    assert resp.status_code not in (401, 403)


# ---- endpoint behavior (all local requests, no token) ------------------------
def test_requests_endpoint_returns_rows(tmp_path, monkeypatch):
    client, store = make_client(tmp_path, monkeypatch, token=None)
    store.add(_row("t1"))
    store.add(_row("t2"))

    resp = client.get("/metrics/requests", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert len(body) == 2
    assert body[0]["trace_id"] == "t2"  # newest first


def test_requests_endpoint_respects_limit(tmp_path, monkeypatch):
    client, store = make_client(tmp_path, monkeypatch, token=None)
    for i in range(5):
        store.add(_row(f"t{i}"))

    resp = client.get(
        "/metrics/requests?limit=2", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}
    )
    assert len(resp.get_json()) == 2


def test_delete_clears_metrics(tmp_path, monkeypatch):
    client, store = make_client(tmp_path, monkeypatch, token=None)
    store.add(_row("t1"))

    resp = client.delete("/metrics", environ_overrides={"REMOTE_ADDR": "127.0.0.1"})
    assert resp.status_code == 200
    assert resp.get_json() == {"cleared": True}
    assert store.recent() == []


def test_summary_reflects_stored_rows(tmp_path, monkeypatch):
    client, store = make_client(tmp_path, monkeypatch, token=None)
    store.add(_row("t1", total_ms=100.0))
    store.add(_row("t2", total_ms=300.0, status="error"))

    summary = client.get(
        "/metrics/summary", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}
    ).get_json()
    assert summary["count"] == 2
    assert summary["error_rate"] == pytest.approx(0.5)
