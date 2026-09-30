![Tests](https://github.com/KritiikaaR/DocAssist/actions/workflows/tests.yml/badge.svg)

# DocAssist

A document question-answering assistant. Upload PDFs or text files and ask questions about them — answers are generated only from the retrieved passages, with citations back to the source file.

Built with Flask, LangChain, FAISS, and GPT-4o, with a React frontend.

---

## Features

**Grounded answers with source attribution.** Every document gets its own FAISS index rather than being merged into one shared store. Retrieval runs per document, then scored chunks are pooled and ranked globally so answers pull the strongest passages across the whole corpus while still knowing which file each came from.

**Scanned PDF recovery.** Standard PDF parsing returns nothing for image-based documents. DocAssist detects these by word density — under 50 words per page on average — and re-extracts the text through Tesseract OCR, preserving page and source metadata.

**Multi-turn conversations.** Follow-up questions like "what about the second one?" are rewritten into standalone search queries using the last 8 turns of chat history, so retrieval doesn't lose context between messages.

**Token streaming.** Responses stream token by token from Flask over server-sent events to the React frontend, so answers appear as they're generated rather than after a long wait.

**Document management.** Uploaded documents and their vector indexes persist across restarts. Past documents can be reactivated in one click, and questions can be scoped to a chosen subset of files.

**Quiz mode.** Generates multiple-choice and true/false questions at three difficulty levels from selected documents, validates the model's JSON output against the expected schema before use, and grades answers with explanations.

---

## Architecture

```
Upload  ->  Parse (PyPDF / OCR fallback)  ->  Chunk (800 chars, 100 overlap)
        ->  Embed (OpenAI)  ->  FAISS index per document

Question  ->  Condense with chat history  ->  Search each active index
          ->  Pool and rank globally, take top 6  ->  GPT-4o  ->  Stream to client
```

**Why one index per document instead of one merged store:** a merged store returns the closest chunks but loses reliable per-file attribution. Keeping indexes separate preserves the source of every chunk, and ranking the pooled results afterward recovers the cross-document comparison a merged store would have given.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Flask, LangChain, FAISS, OpenAI GPT-4o |
| OCR | Tesseract, Poppler |
| Frontend | React, Vite |
| Streaming | Server-sent events, Fetch Streams API |
| Tracing | OpenLLMetry (Traceloop SDK), Jaeger, SQLite |
| Container | Docker |

---

## Running it

### With Docker (recommended)

```bash
cd backend
docker build -t docassist .
docker run --rm -p 5000:5000 --env-file .env docassist
```

Then, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The container image includes the system libraries the app depends on beyond pip packages: `tesseract-ocr` and `poppler-utils` for OCR, and `libgomp1` for FAISS.

### Without Docker

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Requires Tesseract and Poppler installed on the host.

### Environment

Create `backend/.env`:

```
OPENAI_API_KEY=your-key-here
```

No spaces around `=` — Docker's `--env-file` parser rejects them.

---

## Observability

Every chat and quiz request is traced with [OpenLLMetry](https://github.com/traceloop/openllmetry) (`traceloop-sdk`), rolled up into one SQLite row per request, and exposed at `/metrics/summary` and `/metrics/requests` for a `/metrics` dashboard. Spans optionally export to Jaeger for full-trace inspection.

### Architecture

```
chat_query (workflow)                    quiz_generate (workflow)
├── condense_question (task)*            ├── retrieve (task)
├── retrieve (task)                      └── generate (task)
├── generate (task)  — records TTFT
└── evaluate (task)  — groundedness

* only when the request has prior chat history

Every span  ->  Jaeger (OTLP, optional)
            ->  MetricsCollector  ->  SQLite (one row per request)
                                   ->  GET /metrics/summary, GET /metrics/requests
```

`Instruments.LANGCHAIN` and `Instruments.OPENAI` auto-instrument LangChain's chain calls and the OpenAI client underneath, so model name and token counts show up for free. `chat_query`/`quiz_generate` and their steps are DocAssist's own spans layered on top of that, so a trace reads as a pipeline instead of a flat pile of framework spans.

Chat answers stream over SSE, so `chat_query`'s spans are opened by hand (`observability/tracing.py`'s `traced_step`) rather than with the `@workflow`/`@task` decorators — those only wrap a function *call*, and applied to a generator function would just span the near-instant creation of the generator object, not the token-by-token loop that actually runs while Flask drains it. Quiz generation is a normal blocking call, so it uses the real decorators — the codebase ends up demonstrating both techniques.

### Running Jaeger

```bash
docker-compose up
```

Starts Jaeger (UI at http://localhost:16686, OTLP receiver on port 4318) and the backend together. The backend also runs fine entirely on its own — tracing to Jaeger just won't happen (see below).

Requests from your host reach the backend container via the Docker network (e.g. `172.x`), not `127.0.0.1`, so the loopback-only access rule below would `403` you even on your own machine. `docker-compose.yml` sets a dev-only `METRICS_ADMIN_TOKEN` (`docassist-dev-token` by default — export `METRICS_ADMIN_TOKEN` on the host before `docker-compose up` to pick your own) to route around that.

### Env vars

| Var | Default | What it does |
|---|---|---|
| `TRACING_ENABLED` | `1` | Export spans to Jaeger. `0` keeps the SQLite rollup (and `/metrics/*`) working without ever trying to reach Jaeger. |
| `OTLP_ENDPOINT` | `http://localhost:4318` | Where Jaeger accepts OTLP over HTTP. |
| `METRICS_DB_PATH` | `backend/metrics.db` | SQLite file the rollup is written to. |
| `METRICS_ADMIN_TOKEN` | unset | Required (as an `X-Metrics-Token` header or `?token=` param) to reach `/metrics/*` from anywhere but localhost. **Unset in production means `/metrics/*` only answers loopback requests** — set this before exposing the backend publicly. |

Tracing is designed to never take the app down: if Jaeger isn't running, or `Traceloop.init()` itself fails, `init_tracing()` logs a warning and the app runs exactly as if tracing were off. Render (no Jaeger there) relies on this.

### Dashboard

Set `VITE_METRICS_ENABLED=true` (frontend `.env`) to show the "Metrics" card on the landing page and enable the `/metrics` route. It shows p50/p95 latency, time-to-first-token, cost per request, average tokens, groundedness, error rate, a "where the time goes" step breakdown, a latency trend, and a table of recent requests linking out to their trace in Jaeger (needs `VITE_JAEGER_URL`, default `http://localhost:16686`).

If `METRICS_ADMIN_TOKEN` is set on the backend, the dashboard prompts for it at runtime (a 401 triggers a small "enter admin token" form) rather than reading it from a build-time env var — Vite inlines `import.meta.env.*` into the shipped JS bundle, so a build-time token would just be sitting in plain text in devtools for anyone to read. The entered token lives only in React state for that page load; nothing is written to localStorage, sessionStorage, or a cookie.

![Metrics dashboard](docs/metrics-dashboard.png)
*(screenshot placeholder — run the app, ask a few questions, and drop a screenshot of `/metrics` here)*

### Benchmark

```bash
cd backend
python scripts/benchmark.py --doc sample.pdf --n 30 --reset

# against the dockerized backend, pass the same token docker-compose set:
METRICS_ADMIN_TOKEN=docassist-dev-token python scripts/benchmark.py --doc sample.pdf --n 30
```

Uploads a document, fires 30 questions at it, and prints p50/p95 latency, TTFT, average tokens, cost per request, and groundedness — both the client's own stopwatch timing and the server's trace-derived numbers, as a cross-check on each other.

### Groundedness

The default check (`observability/eval.py`) is a cheap word-overlap score — no extra LLM call, no extra cost — kept behind a single function signature so it can be swapped for an LLM-as-judge later without touching call sites.

---

## Notes

Dependency versions are pinned. `faiss-cpu` is compiled against NumPy 1.x and fails to import under NumPy 2.x, and `langchain-openai` requires an `httpx` version that still accepts the `proxies` argument.

**SQLite metrics are ephemeral on Render's free/starter tier.** Without a paid persistent Disk attached, `/metrics` history resets on every deploy or restart. Fine for a demo; don't rely on it as a long-term record.

---

## Roadmap

- Retrieval evaluation set with recall@k measurement
- LLM-as-judge groundedness, compared against the word-overlap baseline
- Replace flat-file document tracking with SQLite
- Deploy with rate limiting and a spend cap
