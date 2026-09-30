# Retrieval top_k benchmark — RETRIEVAL_TOP_K=6 vs 3

**Date:** 2026-09-30
**Model:** `gpt-4o` (chat), `text-embedding-3-small` (embeddings)
**Backend:** local (`python app.py`), Jaeger via `docker-compose up -d jaeger`
**Requests:** 30 per run × 6 runs = **180 total** (3 runs at `RETRIEVAL_TOP_K=6`, 3 at `RETRIEVAL_TOP_K=3`)
**Real cost:** **$0.4957** total across all 6 runs (estimated beforehand: ~$0.70–$1.00 — actual came in lower)

## Test documents (all 3 active simultaneously, every request)

| File | Pages | Chunks |
|---|---|---|
| `Introduction to Database.pdf` | 4 | 11 |
| `CE305_SIgnaturePaper_19702_Kritika.pdf` (general vs. AI microprocessors) | 5 | 15 |
| `Midterm Exam.pdf` (CS380 Operating Systems) | 12 | 33 |

30 questions per run (`benchmarks/questions.txt`) — roughly even coverage across all 3 documents plus 3 that deliberately span more than one document, to exercise cross-document retrieval.

## Methodology

- **`RETRIEVAL_TOP_K`** (new env var, `backend/rag.py`) controls the size of the globally pooled, ranked chunk set built from *all* active documents (`_retrieve_with_sources`, line ~308). It does **not** touch the separate, hardcoded per-document search width (`k=4`, line ~299) — that was deliberately left alone.
- **Why 3 documents, not 1:** with only one document active, the per-document `k=4` cap would bind before the global pool ever reached 6 candidates, making `RETRIEVAL_TOP_K=6` indistinguishable from `=4`. With 3 documents active (3 × 4 = up to 12 pooled candidates), both `6` and `3` are genuinely, differently reachable.
- **Chat history cleared before every question** (`POST /history/clear`, added to `scripts/benchmark.py`). Without this, `RAGPipeline.chat_history` accumulates server-side across a run and triggers an extra `condense_question` LLM call on every question after the first — a confound unrelated to `top_k`. Every question in every run here was an independent request.
- **3 runs per setting, not 2** — see the outlier below.
- `RETRIEVAL_TOP_K` was set via env var and the backend restarted between every run so the new value took effect at startup. Default (`6`, i.e. unset) is what ships — unchanged from before this benchmark.

## ⚠️ One outlier, disclosed rather than smoothed over

Run `topk3-runB`, request 29/30 (`"What is busy waiting?"`, trace `dca267c7a5a130855dd9a913d554ceeb`): the **`retrieve` step took 24.78 seconds**, against 600–2000ms everywhere else in all 180 requests.

**What `retrieve` actually does, verified against the installed LangChain source** (not assumed): `RAGPipeline._retrieve_with_sources` loops over every active document and calls FAISS's `similarity_search_with_score(query, k=4)` on each — and that method's first line is `self._embed_query(query)`, a real OpenAI Embeddings API call. With 3 active documents, **one `/query` request makes 3 separate embedding API calls for the same query text** (once per document's FAISS index), all timed inside the `retrieve` span. So this was very likely a transient OpenAI API/network latency spike on one of those three calls — not a local disk or FAISS computation issue (initially suspected, corrected after reading the source).

**What this did and didn't distort**, checked rather than assumed:
- **p50/p95 latency for that run**: not meaningfully affected — percentiles are robust to one outlier out of 30 (`topk3-runB` reported p95 = 3170ms, in line with the other two `top_k=3` runs' 3089ms / 3400ms).
- **That request's tokens, cost, groundedness**: normal (504 input / 40 output tokens, groundedness 1.0) — only its latency was abnormal.
- **`topk3-runB`'s own `time_share_by_step` breakdown**: genuinely skewed (`retrieve: 58%, generate: 42%`, vs. `retrieve: ~40%, generate: ~59–62%` in every other run) — `step_avg_ms` is an arithmetic mean over 30 samples, and one 24.7s value against a ~900ms baseline drags it up. This is why a 3rd run was added per setting instead of discarding data: it dilutes a single run's distortion by a factor of 3 for any statistic derived across runs.
- All 6 run files are kept as-is in `benchmarks/results/` — nothing was deleted or re-run to hide this.

A separate, smaller observation from the same data: one `topk3-runB` request (a cross-document synthesis question) scored **groundedness 0.0** with a 10-token answer — plausibly the model declining to synthesize across unrelated documents rather than a retrieval problem. Not investigated further; noted for completeness since it's an unusually extreme value in the raw data.

## Results (mean of 3 runs per setting; latency also shown as median-of-3-runs, so the one outlier run can't swing the headline number)

| Metric | top_k=6 (mean) | top_k=6 (median) | top_k=3 (mean) | top_k=3 (median) | % change 6→3 |
|---|---|---|---|---|---|
| p50 latency | 2001 ms | **1996 ms** | 2083 ms | **2026 ms** | **+1.50%** (median) |
| p95 latency | 3273 ms | **3072 ms** | 3220 ms | **3170 ms** | **+3.19%** (median) |
| TTFT p50 | 636 ms | **629 ms** | 624 ms | **614 ms** | **−2.38%** (median) |
| Avg tokens/request | 1156.8 | — | 688.8 | — | **−40.46%** |
| Cost/request | $0.003357 | — | $0.002151 | — | **−35.94%** |
| Groundedness | 0.814 | — | 0.759 | — | **−6.80%** |
| Error rate | 0% | — | 0% | — | 0% (0 failures in 180 requests, both settings) |

## Summary

Cutting `RETRIEVAL_TOP_K` from 6 to 3 **cut token usage ~40% and cost ~36% per request**, at a **~7% groundedness cost**, on this 3-document, 30-question set. Latency was essentially a wash — p50/p95/TTFT moved by only 1.5–3.2% in either direction across the two settings, well within the run-to-run noise already visible between same-setting runs (e.g. `top_k=6`'s own p95 ranged 2755–3991ms across its 3 runs). **On this benchmark, `top_k` is a cost/quality lever, not a latency lever** — the dominant cost in both settings is the `generate` step (the GPT-4o call itself), not chunk retrieval or context size in this 3–6 chunk range.

Default stays `RETRIEVAL_TOP_K=6` (unset) — this data doesn't settle which setting to ship; that's a product call weighing the ~7% groundedness drop against the ~36% cost savings.

## Reproduce

```bash
# Jaeger (optional, for trace inspection)
docker-compose up -d jaeger

# Backend — restart between runs to pick up the new env var
cd backend
RETRIEVAL_TOP_K=6 python app.py   # or =3

# In another terminal, per run:
python scripts/benchmark.py \
  --doc "/path/to/Introduction to Database.pdf" \
  --doc "/path/to/CE305_SIgnaturePaper_19702_Kritika.pdf" \
  --doc "/path/to/Midterm Exam.pdf" \
  --questions-file benchmarks/questions.txt \
  --n 30 --reset
```

Raw output of all 6 runs: `benchmarks/results/topk{6,3}-run{A,B,C}.txt`.
