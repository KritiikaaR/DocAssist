"""Environment-driven settings for tracing and metrics.

Same code runs locally, in Docker (docker-compose.yml), and on Render — only the
env vars differ.
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

APP_NAME = os.getenv("OTEL_APP_NAME", "docassist")

# Gates whether spans are exported to Jaeger over OTLP. The in-process metrics
# rollup (SQLite + /metrics/*) keeps working either way — this only controls the
# network export, which must never be required for the app to run.
TRACING_ENABLED = os.getenv("TRACING_ENABLED", "1") == "1"
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4318")

METRICS_DB_PATH = os.getenv("METRICS_DB_PATH", str(BACKEND_DIR / "metrics.db"))

# METRICS_ADMIN_TOKEN gates access to /metrics/* — see observability/auth.py,
# which reads it directly (not from here) so it can be rotated without a
# process restart.
