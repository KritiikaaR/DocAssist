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

## Notes

Dependency versions are pinned. `faiss-cpu` is compiled against NumPy 1.x and fails to import under NumPy 2.x, and `langchain-openai` requires an `httpx` version that still accepts the `proxies` argument.

---

## Roadmap

- Retrieval evaluation set with recall@k measurement
- Unit tests for chunking, OCR detection, and quiz schema validation
- Replace flat-file document tracking with SQLite
- Deploy with rate limiting and a spend cap