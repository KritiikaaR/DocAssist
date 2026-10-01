"""SSE framing (sse.py).

Context for this test file: a reported bug ("markdown renders as one squished
paragraph") looked like it could be lost newlines in the SSE stream. Diagnosis
(done by capturing the real raw bytes off the wire, not just reading the code)
showed the encoding was already correct — the actual bug was CSS
(.bubble-text had no white-space rule, so a *correctly transmitted* newline
got collapsed by the browser). This file is the regression guard for the part
that could actually break: a token containing a literal newline must not
split one SSE event into two broken ones.
"""
import json

from sse import sse_event


def _parse_like_frontend(raw: str) -> list[dict]:
    """Mirrors App.jsx's SSE parsing loop exactly: split on \\n, keep lines
    starting with "data: ", JSON.parse what follows. If this and sse_event()
    don't agree, a real browser wouldn't either."""
    events = []
    for line in raw.split("\n"):
        if not line.startswith("data: "):
            continue
        events.append(json.loads(line[len("data: "):]))
    return events


def test_sse_event_is_well_formed():
    assert sse_event({"token": "hello"}) == 'data: {"token": "hello"}\n\n'


def test_token_with_newline_stays_on_one_physical_line():
    """The whole point of JSON-encoding the payload: a raw newline inside the
    token would otherwise split the `data:` line in two, breaking the SSE
    frame. json.dumps escapes it as the two-character sequence \\n instead."""
    line = sse_event({"token": "- item one\n"})
    body = line.rstrip("\n")  # strip the SSE frame's blank-line terminator
    assert "\n" not in body
    assert body.startswith("data: ")


def test_token_with_newline_round_trips_through_frontend_parsing():
    raw = sse_event({"token": "- first item\n- second item"})
    events = _parse_like_frontend(raw)
    assert events == [{"token": "- first item\n- second item"}]


def test_sources_sentinel_with_multiline_snippet_round_trips():
    raw = sse_event({"done": True, "sources": [{"filename": "a.pdf", "snippet": "line one\nline two"}]})
    events = _parse_like_frontend(raw)
    assert events == [{"done": True, "sources": [{"filename": "a.pdf", "snippet": "line one\nline two"}]}]


def test_error_event_with_newline_round_trips():
    raw = sse_event({"error": "boom\nwith a newline"})
    events = _parse_like_frontend(raw)
    assert events == [{"error": "boom\nwith a newline"}]


def test_multiple_events_in_one_stream_parse_independently():
    """A real stream is many sse_event() calls concatenated — the blank-line
    separators must keep them independent even when individual tokens carry
    newlines of their own."""
    raw = sse_event({"token": "a\n"}) + sse_event({"token": "b"}) + sse_event({"done": True, "sources": []})
    events = _parse_like_frontend(raw)
    assert events == [{"token": "a\n"}, {"token": "b"}, {"done": True, "sources": []}]
