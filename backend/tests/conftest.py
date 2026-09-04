"""
Shared pytest fixtures.

pytest loads this file automatically. Any fixture defined here is available
to every test file in this folder without importing it.
"""

import os
import sys

import pytest
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Make rag.py importable when running pytest from the backend folder.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rag import RAGPipeline  # noqa: E402


@pytest.fixture
def pipeline():
    """
    A RAGPipeline with no OpenAI clients attached.

    RAGPipeline.__init__ builds OpenAIEmbeddings and ChatOpenAI, which need an
    API key and would make these tests cost money and require a network. We
    bypass __init__ with object.__new__ and set only the attributes the pure
    logic under test actually uses.
    """
    p = object.__new__(RAGPipeline)
    p.splitter = RecursiveCharacterTextSplitter(
        chunk_size=800, chunk_overlap=100, separators=["\n\n", "\n", ".", " "]
    )
    p.vectorstores = {}
    p.active_docs = []
    p.session_docs = []
    p.history_docs = []
    p.chat_history = []
    return p


class FakeDoc:
    """Stands in for a langchain Document — only page_content is read."""

    def __init__(self, page_content):
        self.page_content = page_content


class FakeDocstore:
    def __init__(self, docs):
        self._dict = {str(i): d for i, d in enumerate(docs)}


class FakeVectorstore:
    """Minimal stand-in for a FAISS store, for word counting."""

    def __init__(self, texts):
        self.docstore = FakeDocstore([FakeDoc(t) for t in texts])


@pytest.fixture
def make_docs():
    """Builds a list of fake documents, each with `words_per_page` words."""

    def _make(page_count, words_per_page):
        return [FakeDoc(" ".join(["word"] * words_per_page)) for _ in range(page_count)]

    return _make
