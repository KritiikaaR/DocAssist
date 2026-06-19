# HealthDoc RAG Assistant

An AI-powered document Q&A tool built with LangChain, FAISS, GPT-4o, and React.  
Upload health plan documents (PDF or TXT) and ask questions in natural language.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React + Vite |
| Backend | Flask + Python |
| LLM | OpenAI GPT-4o |
| Orchestration | LangChain |
| Vector Store | FAISS |
| Embeddings | OpenAI text-embedding-ada-002 |

## Project Structure

```
healthdoc-rag/
├── backend/
│   ├── app.py           # Flask API (upload, query, clear endpoints)
│   ├── rag.py           # RAG pipeline (ingest, embed, retrieve, generate)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── App.jsx      # Main chat UI component
    │   └── App.css      # Styles
    ├── package.json
    └── vite.config.js
```

## Setup

### 1. Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Set your OpenAI API key
cp .env.example .env
# Edit .env and add your key: OPENAI_API_KEY=sk-...

# Run the server
python app.py
# Backend runs at http://localhost:5000
```

### 2. Frontend

```bash
cd frontend

npm install
npm run dev
# Frontend runs at http://localhost:5173
```

### 3. Usage

1. Open `http://localhost:5173` in your browser
2. Upload a PDF or TXT health plan document using the sidebar
3. Wait for ingestion confirmation
4. Type your question in the chat box and press Enter

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/upload` | Upload and ingest a document |
| POST | `/query` | Ask a question |
| GET | `/documents` | List ingested documents |
| POST | `/clear` | Clear the vector store |

## How It Works

1. **Ingestion**: Uploaded files are split into 800-token chunks with 100-token overlap using `RecursiveCharacterTextSplitter`
2. **Embedding**: Each chunk is embedded using OpenAI's `text-embedding-ada-002` model
3. **Storage**: Embeddings are stored in a FAISS index and persisted to disk
4. **Retrieval**: On each query, the top-4 most similar chunks are retrieved via cosine similarity
5. **Generation**: Retrieved chunks + the user question are sent to GPT-4o with a domain-specific prompt

## Environment Variables

```
OPENAI_API_KEY=your_openai_api_key_here
```
