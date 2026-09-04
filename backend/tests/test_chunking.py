"""
Tests for the text splitter — how documents are broken into chunks
before being embedded.
"""

from langchain_core.documents import Document


def test_short_document_stays_one_chunk(pipeline):
    doc = Document(page_content="A short paragraph that fits well under the limit.")
    chunks = pipeline.splitter.split_documents([doc])
    assert len(chunks) == 1


def test_long_document_is_split(pipeline):
    doc = Document(page_content=" ".join(["word"] * 1000))
    chunks = pipeline.splitter.split_documents([doc])
    assert len(chunks) > 1


def test_no_chunk_exceeds_chunk_size(pipeline):
    doc = Document(page_content=" ".join(["word"] * 2000))
    chunks = pipeline.splitter.split_documents([doc])
    assert all(len(c.page_content) <= 800 for c in chunks)


def test_metadata_is_preserved(pipeline):
    """Source attribution depends on metadata surviving the split."""
    doc = Document(
        page_content=" ".join(["word"] * 1000),
        metadata={"source": "report.pdf", "page": 3},
    )
    chunks = pipeline.splitter.split_documents([doc])
    assert all(c.metadata["source"] == "report.pdf" for c in chunks)


def test_empty_document_produces_no_chunks(pipeline):
    """ingest() relies on this to raise a clear error for unreadable files."""
    doc = Document(page_content="")
    chunks = pipeline.splitter.split_documents([doc])
    assert chunks == []
