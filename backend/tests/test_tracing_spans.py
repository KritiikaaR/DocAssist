"""End-to-end (mocked LLM, no network): run a real query_stream()/generate_quiz()
call and check what the tracing layer actually recorded.

Traceloop.init() sets a global OpenTelemetry TracerProvider, which can only
happen once per process — so it's initialized once here at module import time,
with tracing's Jaeger export disabled and an in-memory exporter attached
instead, mirroring the pattern in ragscope's tests/conftest.py.
"""
import os

os.environ.setdefault("TRACELOOP_TELEMETRY", "false")

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from observability.store import RequestStore
from observability.tracing import ENTITY_NAME, init_tracing
from rag import RAGPipeline

_EXPORTER = InMemorySpanExporter()
_COLLECTOR = init_tracing(
    RequestStore(":memory:"), "http://unused", enabled=False,
    extra_processors=[SimpleSpanProcessor(_EXPORTER)],
)


@pytest.fixture(autouse=True)
def _fresh_store_and_exporter():
    """Every test gets its own store on the shared collector and a clean span list."""
    store = RequestStore(":memory:")
    _COLLECTOR.store = store
    _EXPORTER.clear()
    yield store


def _fake_pipeline(answer="Based on the documents: DocAssist streams answers over SSE."):
    """A RAGPipeline with a fake LangChain chat model instead of a real
    ChatOpenAI, so no network/API key is needed. Same object.__new__ bypass
    the existing `pipeline` fixture in conftest.py uses, for the same reason.
    """
    p = object.__new__(RAGPipeline)
    p.llm = GenericFakeChatModel(messages=iter([AIMessage(content=answer)] * 10))
    p.vectorstores = {"doc.pdf": object()}  # only needs to be truthy
    p.active_docs = ["doc.pdf"]
    p.chat_history = []
    return p


def _span_names(exporter=_EXPORTER):
    return {s.attributes.get(ENTITY_NAME) for s in exporter.get_finished_spans()}


class _FakeDoc:
    def __init__(self, text):
        self.page_content = text


class _FakeDocstore:
    def __init__(self, docs):
        self._dict = {str(i): d for i, d in enumerate(docs)}


class _FakeQuizVectorstore:
    """Enough words in .docstore for generate_quiz's length check to pass, and
    a canned similarity_search result to build quiz context from — mirrors
    conftest.py's FakeVectorstore, extended with the search method the quiz
    path also needs."""

    def __init__(self):
        self.docstore = _FakeDocstore([_FakeDoc(" ".join(["word"] * 150))])

    def similarity_search(self, *_args, **_kwargs):
        return [_FakeDoc("DocAssist streams answers over SSE and supports quiz mode.")]


def test_chat_query_produces_expected_span_tree(monkeypatch):
    rag = _fake_pipeline()
    monkeypatch.setattr(rag, "_retrieve_with_sources", lambda q: ("[Source: doc.pdf]\ncontext", []))

    list(rag.query_stream("What does DocAssist do?"))

    assert {"chat_query", "retrieve", "generate", "evaluate"} <= _span_names()
    assert "condense_question" not in _span_names()  # no chat history yet


def test_chat_query_condenses_when_history_exists(monkeypatch):
    rag = _fake_pipeline()
    rag.chat_history = [HumanMessage(content="earlier"), AIMessage(content="earlier answer")]
    monkeypatch.setattr(rag, "_retrieve_with_sources", lambda q: ("[Source: doc.pdf]\ncontext", []))

    list(rag.query_stream("what about the other one?"))

    assert "condense_question" in _span_names()


def test_generate_span_records_ttft(monkeypatch):
    rag = _fake_pipeline()
    monkeypatch.setattr(rag, "_retrieve_with_sources", lambda q: ("[Source: doc.pdf]\ncontext", []))

    list(rag.query_stream("anything"))

    generate_spans = [s for s in _EXPORTER.get_finished_spans() if s.attributes.get(ENTITY_NAME) == "generate"]
    assert len(generate_spans) == 1
    assert generate_spans[0].attributes["docassist.ttft_ms"] >= 0


def test_collector_writes_one_chat_row(_fresh_store_and_exporter, monkeypatch):
    store = _fresh_store_and_exporter
    rag = _fake_pipeline()
    monkeypatch.setattr(rag, "_retrieve_with_sources", lambda q: ("[Source: doc.pdf]\nDocAssist streams answers.", []))

    list(rag.query_stream("What does DocAssist do?"))

    rows = store.recent()
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "chat"
    assert row["status"] == "ok"
    assert row["question"] == "What does DocAssist do?"
    assert [s["name"] for s in row["steps"]] == ["retrieve", "generate", "evaluate"]
    assert row["ttft_ms"] is not None
    assert 0 <= row["groundedness"] <= 1


def test_failed_generation_is_recorded_as_error(_fresh_store_and_exporter, monkeypatch):
    store = _fresh_store_and_exporter
    rag = _fake_pipeline()
    monkeypatch.setattr(rag, "_retrieve_with_sources", lambda q: ("[Source: doc.pdf]\ncontext", []))

    def boom(*_args, **_kwargs):
        raise RuntimeError("provider timeout")

    # GenericFakeChatModel is a pydantic model, so instance attributes have to
    # be declared fields — patch the class method instead.
    monkeypatch.setattr(GenericFakeChatModel, "stream", boom)

    with pytest.raises(RuntimeError):
        list(rag.query_stream("anything"))

    row = store.recent()[0]
    assert row["status"] == "error"


_QUIZ_JSON = (
    '{"questions": [{"id": "q1", "type": "true_false", "question": "Is this a test?", '
    '"correct_answer": "true", "explanation": "yes"}]}'
)


def test_quiz_generate_produces_expected_span_tree():
    rag = _fake_pipeline(answer=_QUIZ_JSON)
    rag.vectorstores = {"doc.pdf": _FakeQuizVectorstore()}

    quiz = rag.generate_quiz(["doc.pdf"], "easy", ["true_false"], 1)

    assert quiz["questions"][0]["id"] == "q1"
    assert {"quiz_generate", "retrieve", "generate"} <= _span_names()


def test_collector_writes_one_quiz_row_with_no_ttft(_fresh_store_and_exporter):
    store = _fresh_store_and_exporter
    rag = _fake_pipeline(answer=_QUIZ_JSON)
    rag.vectorstores = {"doc.pdf": _FakeQuizVectorstore()}

    rag.generate_quiz(["doc.pdf"], "easy", ["true_false"], 1)

    rows = store.recent()
    assert len(rows) == 1
    assert rows[0]["kind"] == "quiz"
    assert rows[0]["ttft_ms"] is None
