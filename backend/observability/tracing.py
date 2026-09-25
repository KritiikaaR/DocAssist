"""OpenLLMetry setup plus a small span processor that feeds the dashboard.

How the pieces fit together for one request:
  1. init_tracing() turns on OpenTelemetry and auto-instruments LangChain and the
     OpenAI client (Instruments.LANGCHAIN / Instruments.OPENAI), so every chain
     step and every OpenAI call becomes a span with model/token attributes for
     free.
  2. rag.py adds its own spans on top of that, so one request shows a readable
     step-by-step trace instead of a flat pile of auto-instrumented spans:
       - quiz_generate is a normal blocking call, so it uses the real
         @workflow / @task decorators from traceloop.sdk.
       - query_stream is a *generator* consumed one token at a time by Flask's
         SSE loop. The @workflow/@task decorators only wrap a function call —
         applied to a generator function they'd span the cheap creation of the
         generator object, not its iteration. So the chat path uses
         `traced_step` below: a plain context manager opened by hand around the
         `yield` points, which stays "open" across suspensions the same way any
         `with` block does in a generator.
  3. Every span is sent to up to two places:
       - Jaeger (via OTLP), for clicking into any single trace
       - MetricsCollector (below), which rolls each trace up into one SQLite row
"""
import logging
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

from flask import Blueprint, jsonify, request
from opentelemetry import trace
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.trace import StatusCode

from . import config
from .auth import require_metrics_access
from .metrics import summarize
from .pricing import cost_usd
from .store import RequestStore

logger = logging.getLogger(__name__)

SPAN_KIND = "traceloop.span.kind"
ENTITY_NAME = "traceloop.entity.name"

# The OpenAI instrumentation has used both naming schemes across versions, so read either.
INPUT_TOKEN_KEYS = ("gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")
OUTPUT_TOKEN_KEYS = ("gen_ai.usage.output_tokens", "gen_ai.usage.completion_tokens")
MODEL_KEYS = ("gen_ai.response.model", "gen_ai.request.model")

# entity.name of the root span -> request "kind", so the dashboard doesn't
# average quiz latency (no streaming, much slower) together with chat latency.
ROOT_KIND = {"chat_query": "chat", "quiz_generate": "quiz"}

# entity.name of our own step spans. Traceloop's LangChain instrumentation
# (Instruments.LANGCHAIN) creates its own spans for each Runnable in a chain
# (e.g. "RunnableSequence" for the `PROMPT | llm | StrOutputParser()` pipe),
# and — because Traceloop's LangChain instrumentor deliberately mirrors the
# @workflow/@task decorator's attribute convention — some of those carry the
# exact same traceloop.span.kind="workflow"/"task" attributes ours do. Without
# this whitelist, MetricsCollector would treat LangChain's own internal
# "RunnableSequence" workflow span as if it were our request root (it's nested
# *inside* our "generate" span, so it ends first, triggering a premature
# rollup that loses whatever steps hadn't ended yet), and summarize_trace()
# would list LangChain's internal step names alongside ours. Checking against
# a name we control instead of the raw span-kind sidesteps both problems.
KNOWN_STEPS = {"condense_question", "retrieve", "generate", "evaluate"}
KNOWN_ROOTS = set(ROOT_KIND)

MAX_PENDING_TRACES = 500

_tracer = trace.get_tracer("docassist")


@contextmanager
def traced_step(name: str, kind: str = "task"):
    """Open a span that looks like a @task/@workflow span to MetricsCollector.

    Sets the same traceloop.span.kind / traceloop.entity.name attributes the
    decorators set, so summarize_trace()'s step-detection logic doesn't care
    whether a given span came from a decorator or from here.
    """
    with _tracer.start_as_current_span(name) as span:
        span.set_attribute(SPAN_KIND, kind)
        span.set_attribute(ENTITY_NAME, name)
        yield span


def _first(attrs, keys, default=None):
    for k in keys:
        if k in attrs and attrs[k] is not None:
            return attrs[k]
    return default


def _ms(span: ReadableSpan) -> float:
    return (span.end_time - span.start_time) / 1e6


def summarize_trace(spans: list[ReadableSpan], root: ReadableSpan) -> dict:
    """Collapse all the spans of one request into a single dashboard row."""
    steps = []
    input_tokens = output_tokens = 0
    cost = 0.0
    chat_model = None
    error = None
    ttft_ms = None

    for s in sorted(spans, key=lambda s: s.start_time):
        attrs = s.attributes or {}
        entity_name = attrs.get(ENTITY_NAME, s.name)
        if attrs.get(SPAN_KIND) == "task" and entity_name in KNOWN_STEPS:
            steps.append({"name": entity_name, "ms": round(_ms(s), 2)})
            if entity_name == "generate" and "docassist.ttft_ms" in attrs:
                ttft_ms = attrs["docassist.ttft_ms"]

        i = int(_first(attrs, INPUT_TOKEN_KEYS, 0) or 0)
        o = int(_first(attrs, OUTPUT_TOKEN_KEYS, 0) or 0)
        if i or o:
            model = _first(attrs, MODEL_KEYS)
            input_tokens += i
            output_tokens += o
            cost += cost_usd(model, i, o)
            if model and "embedding" not in model:
                chat_model = model

        if s.status.status_code == StatusCode.ERROR and error is None:
            error = s.status.description or s.name

    root_attrs = root.attributes or {}
    root_entity = root_attrs.get(ENTITY_NAME, root.name)
    return {
        "trace_id": format(root.context.trace_id, "032x"),
        "created_at": root.start_time / 1e9,
        "kind": ROOT_KIND.get(root_entity, root_entity),
        "question": root_attrs.get("docassist.question"),
        "status": "error" if error else "ok",
        "error": error,
        "total_ms": round(_ms(root), 2),
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "steps": steps,
        "model": chat_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": round(cost, 8),
        "groundedness": root_attrs.get("docassist.groundedness"),
    }


class MetricsCollector(SpanProcessor):
    """Buffers spans per trace and writes a summary once the root span finishes.

    Child spans always end before their parent, so by the time the root span
    (kind="workflow") ends we have everything we need for that request.
    """

    def __init__(self, store: RequestStore):
        self.store = store
        self._spans: dict[int, list[ReadableSpan]] = defaultdict(list)
        self._first_seen: dict[int, float] = {}
        self._lock = threading.Lock()

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span: ReadableSpan) -> None:
        tid = span.context.trace_id
        attrs = span.attributes or {}
        # Checking entity.name against KNOWN_ROOTS (not just span.kind ==
        # "workflow") is deliberate — see the KNOWN_STEPS comment above.
        is_root = attrs.get(SPAN_KIND) == "workflow" and attrs.get(ENTITY_NAME) in KNOWN_ROOTS
        with self._lock:
            self._spans[tid].append(span)
            self._first_seen.setdefault(tid, time.time())
            if not is_root:
                self._evict_if_needed()
                return
            spans = self._spans.pop(tid)
            self._first_seen.pop(tid, None)
        self.store.add(summarize_trace(spans, span))

    def _evict_if_needed(self):
        # Spans that never get a workflow-kind parent (e.g. an ingest-time
        # embedding call, which we deliberately don't wrap in a workflow) would
        # otherwise pile up in _spans forever.
        if len(self._spans) <= MAX_PENDING_TRACES:
            return
        oldest = min(self._first_seen, key=self._first_seen.get)
        self._spans.pop(oldest, None)
        self._first_seen.pop(oldest, None)

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def init_tracing(store: RequestStore, otlp_endpoint: str, enabled: bool, extra_processors=None):
    """Start OpenLLMetry. Returns the collector (tests inspect/replace it), or
    None if tracing couldn't start.

    The whole thing is wrapped in one try/except on purpose: a bad OTLP
    endpoint, a Jaeger that isn't running, or an instrumentor/version mismatch
    must never stop the app from starting. Render runs with no Jaeger reachable
    at all, and that has to just work — the app falls back to "no tracing"
    instead of crashing.
    """
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from traceloop.sdk import Traceloop
        from traceloop.sdk.instruments import Instruments

        collector = MetricsCollector(store)
        processors = [collector, *(extra_processors or [])]
        if enabled:
            processors.append(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint.rstrip('/')}/v1/traces"))
            )

        Traceloop.init(
            app_name=config.APP_NAME,
            processor=processors,
            instruments={Instruments.LANGCHAIN, Instruments.OPENAI},
            telemetry_enabled=False,  # don't send anonymous usage stats to Traceloop
            disable_batch=True,
        )
        return collector
    except Exception:
        logger.warning("Tracing disabled: init_tracing() failed", exc_info=True)
        return None


def metrics_blueprint(store: RequestStore) -> Blueprint:
    """GET /metrics/summary, GET /metrics/requests, DELETE /metrics.

    A Blueprint (rather than routes on the main app) so it only depends on
    `store`, not on rag.py's RAGPipeline — that keeps it testable without
    constructing a real RAGPipeline (which needs an OpenAI API key).
    """
    bp = Blueprint("metrics", __name__)
    bp.before_request(require_metrics_access)

    @bp.route("/metrics/summary", methods=["GET"])
    def metrics_summary():
        limit = request.args.get("limit", 200, type=int)
        return jsonify(summarize(store.recent(limit)))

    @bp.route("/metrics/requests", methods=["GET"])
    def metrics_requests():
        limit = request.args.get("limit", 50, type=int)
        return jsonify(store.recent(limit))

    @bp.route("/metrics", methods=["DELETE"])
    def metrics_clear():
        store.clear()
        return jsonify({"cleared": True})

    return bp
