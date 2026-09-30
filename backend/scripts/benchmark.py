"""Fire a batch of questions at the API so the dashboard has real numbers.

Unlike a plain JSON endpoint, /query is server-sent events, so this has to read
the stream itself to measure client-side time-to-first-token and total time —
those are cross-checks against the server-side numbers /metrics/summary reports
(which come from the trace, not from wall-clock timing here).

Usage:
    python scripts/benchmark.py --doc sample_docs/rag_basics.md      # 30 requests
    python scripts/benchmark.py --doc mydoc.pdf --n 100 --reset
    python scripts/benchmark.py --doc a.pdf --doc b.pdf --doc c.pdf --n 30   # multiple docs active at once

Run it once, change ONE thing (chunk size, model, prompt), run it again, and
compare p95 + cost per request. That before/after is your resume bullet.
"""
import argparse
import json
import os
import random
import statistics
import time

import httpx

QUESTIONS = [
    "What is this document about?",
    "Summarize the main points in a few sentences.",
    "What are the key takeaways?",
    "Are there any specific numbers or dates mentioned?",
    "What questions does this document answer?",
    "Explain the most important concept covered here.",
    "Who is the intended audience for this document?",
    "What would someone need to know before reading this?",
    "Is there anything unusual or noteworthy in this document?",
    "What's the overall conclusion or recommendation?",
]


def load_questions(path: str | None) -> list[str]:
    if not path:
        return QUESTIONS
    with open(path, encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    return lines or QUESTIONS


def upload_doc(client: httpx.Client, doc_path: str) -> str:
    filename = os.path.basename(doc_path)
    with open(doc_path, "rb") as f:
        resp = client.post("/upload", files={"file": (filename, f)})
    resp.raise_for_status()
    body = resp.json()
    print(f"Uploaded '{filename}' -> {body.get('chunks')} chunks, used_ocr={body.get('used_ocr')}")
    return filename


def activate_docs(client: httpx.Client, filenames: list[str]) -> None:
    """Explicitly set the active-document set rather than relying on upload's
    implicit auto-activate — makes it obvious which documents every question
    in the run is retrieving against, regardless of upload order."""
    resp = client.post("/documents/active", json={"docs": filenames})
    resp.raise_for_status()
    active = resp.json().get("active", [])
    print(f"Active documents: {active}")
    missing = set(filenames) - set(active)
    if missing:
        raise RuntimeError(f"Failed to activate: {missing}")


def ask_and_time(client: httpx.Client, question: str) -> dict:
    """Clears server-side chat history first so every question is an
    independent request — otherwise RAGPipeline.chat_history accumulates
    across the whole run (it's never reset between unrelated questions),
    which would add an extra condense_question LLM call on every question
    after the first and make cost/token numbers incomparable across runs.
    Then streams /query and returns client-side timing + whether it succeeded.
    """
    client.post("/history/clear").raise_for_status()

    t0 = time.perf_counter()
    ttft = None
    failed = False

    with client.stream("POST", "/query", json={"question": question}) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line or not raw_line.startswith("data: "):
                continue
            payload = json.loads(raw_line[len("data: "):])
            if "error" in payload:
                failed = True
            elif "token" in payload and ttft is None:
                ttft = (time.perf_counter() - t0) * 1000
            elif "done" in payload:
                break

    total_ms = (time.perf_counter() - t0) * 1000
    return {"total_ms": total_ms, "ttft_ms": ttft, "failed": failed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument(
        "--doc", required=True, action="append",
        help="path to a PDF or TXT file to index before asking questions; "
             "repeat to activate multiple documents at once",
    )
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--questions-file", help="one question per line; defaults to a generic built-in set")
    ap.add_argument("--reset", action="store_true", help="clear stored metrics before running")
    ap.add_argument(
        "--token", default=os.getenv("METRICS_ADMIN_TOKEN"),
        help="X-Metrics-Token, if the backend requires one (e.g. the dev token "
             "docker-compose.yml sets — export METRICS_ADMIN_TOKEN to match it "
             "instead of passing this every time)",
    )
    args = ap.parse_args()

    questions = load_questions(args.questions_file)
    headers = {"X-Metrics-Token": args.token} if args.token else {}

    with httpx.Client(base_url=args.url, timeout=60, headers=headers) as client:
        filenames = [upload_doc(client, doc) for doc in args.doc]
        activate_docs(client, filenames)

        if args.reset:
            client.delete("/metrics").raise_for_status()

        client_totals, client_ttfts, failures = [], [], 0
        for i in range(args.n):
            q = random.choice(questions)
            result = ask_and_time(client, q)
            failures += result["failed"]
            client_totals.append(result["total_ms"])
            if result["ttft_ms"] is not None:
                client_ttfts.append(result["ttft_ms"])
            print(f"[{i + 1}/{args.n}] {result['total_ms']:.0f}ms "
                  f"(ttft {result['ttft_ms'] or 0:.0f}ms)  {q}")

        summary = client.get("/metrics/summary").json()

    print("\n--- results ---")
    print(f"client-side median total:  {statistics.median(client_totals):.0f} ms, failures: {failures}")
    if client_ttfts:
        print(f"client-side median TTFT:   {statistics.median(client_ttfts):.0f} ms")
    print(f"server p50 / p95 total:     {summary['p50_ms']:.0f} / {summary['p95_ms']:.0f} ms")
    print(f"server p50 / p95 TTFT:      {summary['ttft_p50_ms']:.0f} / {summary['ttft_p95_ms']:.0f} ms")
    print(f"avg tokens:                 {summary['avg_tokens']}")
    print(f"avg cost/request:           ${summary['avg_cost_usd']:.6f}")
    print(f"groundedness:                {summary['avg_groundedness']}")
    print(f"error rate:                  {summary['error_rate']:.0%}")
    print("time share by step:", {k: f"{v:.0%}" for k, v in summary["step_share"].items()})


if __name__ == "__main__":
    main()
