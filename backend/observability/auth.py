"""Access control for /metrics/*.

These endpoints expose every question a user has asked, and DELETE wipes stored
metrics, so they can't be open on a public deployment.

- METRICS_ADMIN_TOKEN set: every request must present it, via an X-Metrics-Token
  header or a ?token= query param (the query param exists so a plain browser
  link still works; the dashboard's own fetches use the header). Mismatch or
  missing token -> 401.
- METRICS_ADMIN_TOKEN unset: only loopback requests are allowed. This is the
  "local dev only" fallback — a deployment that forgets to set the token fails
  closed instead of quietly being world-readable.
"""
import os

from flask import jsonify, request

_LOOPBACK = {"127.0.0.1", "::1"}


def require_metrics_access():
    # The dashboard sends X-Metrics-Token as a real header (not just ?token=),
    # which makes the browser precede the actual request with a CORS preflight
    # OPTIONS. That preflight carries no token — it's the browser asking
    # permission to send the real request, not the request itself — so it must
    # be let through for Flask-CORS to answer it, or every token-authenticated
    # fetch fails at the network level before Flask ever sees a real request.
    if request.method == "OPTIONS":
        return None

    # Read fresh per request (not a config-module snapshot) so a token can be
    # rotated without a process restart, and so tests can flip it with
    # monkeypatch.setenv without needing to reload any module.
    token = os.getenv("METRICS_ADMIN_TOKEN")
    if token:
        supplied = request.headers.get("X-Metrics-Token") or request.args.get("token")
        if supplied != token:
            return jsonify({"error": "Invalid or missing metrics token"}), 401
        return None

    if request.remote_addr not in _LOOPBACK:
        return jsonify({"error": "Metrics are local-only until METRICS_ADMIN_TOKEN is set"}), 403
    return None
