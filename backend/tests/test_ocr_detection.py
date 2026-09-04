"""
Tests for _looks_scanned — the check that decides whether a PDF needs OCR.

A PDF whose pages average under MIN_WORDS_PER_PAGE (50) words is treated as
scanned or image-based, because the normal text parser found almost nothing.
"""

from rag import MIN_WORDS_PER_PAGE


def test_text_pdf_is_not_flagged(pipeline, make_docs):
    """A normal text PDF with plenty of words should not trigger OCR."""
    documents = make_docs(page_count=5, words_per_page=400)
    assert pipeline._looks_scanned(documents) is False


def test_scanned_pdf_is_flagged(pipeline, make_docs):
    """A scanned PDF yields almost no extractable text, so OCR should trigger."""
    documents = make_docs(page_count=5, words_per_page=3)
    assert pipeline._looks_scanned(documents) is True


def test_empty_document_list_is_flagged(pipeline):
    """No pages at all means nothing was extracted — treat it as scanned."""
    assert pipeline._looks_scanned([]) is True


def test_average_is_used_not_per_page(pipeline, make_docs):
    """
    One empty page among full ones should not trigger OCR.

    This guards the difference between checking each page and checking the
    average — a title page or a blank back page is normal in a text PDF.
    """
    documents = make_docs(page_count=4, words_per_page=400) + make_docs(1, 0)
    assert pipeline._looks_scanned(documents) is False


def test_threshold_boundary(pipeline, make_docs):
    """Exactly at the threshold is not scanned; one word below is."""
    at_threshold = make_docs(page_count=1, words_per_page=MIN_WORDS_PER_PAGE)
    below = make_docs(page_count=1, words_per_page=MIN_WORDS_PER_PAGE - 1)

    assert pipeline._looks_scanned(at_threshold) is False
    assert pipeline._looks_scanned(below) is True
