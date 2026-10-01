"""Server-sent event framing for the streaming endpoints.

One line per the SSE spec: a `data:` field, JSON-encoded, terminated by a
blank line. The JSON encoding is what makes this safe for arbitrary token
content — json.dumps escapes newlines (and any other control characters) as
the two-character sequence \\n *inside* the string, so a token like "- item\n"
never produces a literal line break inside the `data:` line, which would
otherwise split one SSE event into two broken ones. The frontend's
`JSON.parse` on the matching line reverses this, so a real newline character
survives the full round trip.

No RAGPipeline/OpenAI imports here on purpose — this stays trivially safe to
import in tests (see tests/test_sse.py), the same reason observability/*.py
has no heavy imports either.
"""
import json


def sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"
