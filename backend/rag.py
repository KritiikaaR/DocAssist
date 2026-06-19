import os
import shutil
from typing import List, Dict, Any, Generator

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import HumanMessage, AIMessage

VECTORSTORE_DIR = "vectorstore"
UPLOAD_DIR = "uploads"
DOCS_FILE = "ingested_docs.txt"

# Main answer prompt — context chunks are labeled with their source file
MEMORY_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are DocAssist, an AI that helps users understand uploaded documents.

Answer using ONLY the context below. If the answer isn't found, say "I couldn't find that information in the uploaded documents."

Each context chunk is prefixed with [Source: filename]. You may mention which document contains specific information when it helps the user — but only if it adds clarity. Do not mention sources for every sentence.

Context:
{context}"""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "{question}"),
])

# Rewrites follow-up questions into standalone search queries
CONDENSE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Given the conversation history and a follow-up question, rewrite the follow-up as a self-contained search query that captures all the context needed to retrieve relevant document chunks.

Rules:
- Resolve pronouns and vague references ("it", "that", "those recommendations", "the attack", "the other PDF") using the conversation.
- If the question is already standalone, return it unchanged.
- Return ONLY the rewritten query — no explanation, no preamble."""),
    MessagesPlaceholder(variable_name="history"),
    ("human", "Follow-up: {question}\n\nStandalone search query:"),
])

SUMMARY_PROMPT = ChatPromptTemplate.from_messages([
    ("human", """You are DocAssist. Based on the document content below, provide a clear and concise summary.
Cover the main topics, key points, and purpose of the document in 3-5 sentences.

Document content:
{context}

Summary:"""),
])

SUGGEST_PROMPT = ChatPromptTemplate.from_messages([
    ("human", """Based on this document content from "{filename}", generate exactly 3 short, specific, interesting questions a user might want to ask about it.

Rules:
- Each question must be answerable from the document
- Keep each question under 12 words
- Make them specific, not generic like "what is this about?"
- Return ONLY the 3 questions, one per line, no numbering, no bullets

Document content:
{context}

3 questions:"""),
])


class RAGPipeline:
    def __init__(self):
        self.embeddings = OpenAIEmbeddings(openai_api_key=os.getenv("OPENAI_API_KEY"))
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=os.getenv("OPENAI_API_KEY"))
        self.vectorstores: Dict[str, Any] = {}
        self.active_docs: List[str] = []
        self.session_docs: List[str] = []
        self.history_docs: List[str] = []
        self.chat_history: List = []
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, chunk_overlap=100, separators=["\n\n", "\n", ".", " "]
        )
        self._load_state()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load_state(self):
        """On startup: read doc names into history only. No vectorstores loaded into memory."""
        if os.path.exists(DOCS_FILE):
            with open(DOCS_FILE, "r") as f:
                self.history_docs = [l.strip() for l in f if l.strip()]

    def _save_state(self):
        all_docs = self.session_docs + [d for d in self.history_docs if d not in self.session_docs]
        with open(DOCS_FILE, "w") as f:
            f.write("\n".join(all_docs))

    # ── ingestion ─────────────────────────────────────────────────────────────

    def ingest(self, filepath: str) -> tuple[int, list[str]]:
        ext = os.path.splitext(filepath)[1].lower()
        if ext == ".pdf":
            loader = PyPDFLoader(filepath)
        elif ext == ".txt":
            loader = TextLoader(filepath, encoding="utf-8")
        else:
            raise ValueError(f"Unsupported file type: {ext}")

        documents = loader.load()
        chunks = self.splitter.split_documents(documents)
        if not chunks:
            raise ValueError("No text content could be extracted from the file.")

        filename = os.path.basename(filepath)
        vs = FAISS.from_documents(chunks, self.embeddings)
        save_path = os.path.join(VECTORSTORE_DIR, filename)
        os.makedirs(save_path, exist_ok=True)
        vs.save_local(save_path)
        self.vectorstores[filename] = vs

        if filename in self.history_docs:
            self.history_docs.remove(filename)
        if filename not in self.session_docs:
            self.session_docs.append(filename)
        if filename not in self.active_docs:
            self.active_docs.append(filename)
        self._save_state()

        questions = self._generate_questions(filename, chunks[:6])
        return len(chunks), questions

    def activate_from_history(self, filename: str):
        """Move a history doc back into the active session.

        Loads from saved vectorstore if available; otherwise re-ingests from uploads.
        """
        vs_path = os.path.join(VECTORSTORE_DIR, filename)
        loaded = False

        if os.path.exists(vs_path):
            try:
                vs = FAISS.load_local(vs_path, self.embeddings, allow_dangerous_deserialization=True)
                self.vectorstores[filename] = vs
                loaded = True
            except Exception:
                pass

        if not loaded:
            upload_path = os.path.join(UPLOAD_DIR, filename)
            if not os.path.exists(upload_path):
                raise ValueError(
                    f"Vectorstore for '{filename}' is missing and the original file is not in uploads. "
                    "Please re-upload the document."
                )
            self.ingest(upload_path)
            return  # ingest() already updates session_docs / active_docs

        if filename in self.history_docs:
            self.history_docs.remove(filename)
        if filename not in self.session_docs:
            self.session_docs.append(filename)
        if filename not in self.active_docs:
            self.active_docs.append(filename)

    def _generate_questions(self, filename: str, chunks) -> list[str]:
        try:
            context = "\n\n".join(c.page_content for c in chunks)
            chain = SUGGEST_PROMPT | self.llm | StrOutputParser()
            result = chain.invoke({"context": context, "filename": filename})
            questions = [q.strip() for q in result.strip().split("\n") if q.strip()]
            return questions[:3]
        except Exception as e:
            print(f"[DocAssist] question generation failed for '{filename}': {e}", flush=True)
            return []

    # ── active doc management ─────────────────────────────────────────────────

    def set_active_docs(self, docs: List[str]):
        self.active_docs = [d for d in docs if d in self.vectorstores]

    def get_documents(self) -> dict:
        return {"session": self.session_docs, "history": self.history_docs}

    def clear_history(self):
        self.chat_history = []

    # ── retrieval ─────────────────────────────────────────────────────────────

    def _condense_question(self, question: str) -> str:
        """Rewrite a follow-up question into a standalone search query."""
        if not self.chat_history:
            return question
        try:
            chain = CONDENSE_PROMPT | self.llm | StrOutputParser()
            return chain.invoke({"history": self.chat_history[-6:], "question": question}).strip()
        except Exception:
            return question

    def _retrieve_with_sources(self, query: str) -> tuple[str, list[str]]:
        """
        Search each active vectorstore independently, rank all chunks by
        relevance score, and return the best context with source attribution.

        Using per-doc search preserves source info that is lost when stores are merged.
        """
        all_results = []
        for doc_name in self.active_docs:
            vs = self.vectorstores.get(doc_name)
            if not vs:
                continue
            # similarity_search_with_score: L2 distance — lower = more relevant
            pairs = vs.similarity_search_with_score(query, k=4)
            for doc, score in pairs:
                all_results.append((doc, score, doc_name))

        if not all_results:
            return "", []

        # Sort ascending by L2 distance and take the top 6 chunks overall
        all_results.sort(key=lambda x: x[1])
        top = all_results[:6]

        context_parts = []
        source_chunks: List[dict] = []
        seen: set = set()
        for doc, _score, source in top:
            context_parts.append(f"[Source: {source}]\n{doc.page_content}")
            if source not in seen:
                seen.add(source)
                source_chunks.append({
                    "filename": source,
                    "snippet": doc.page_content[:150].strip(),
                })

        return "\n\n---\n\n".join(context_parts), source_chunks

    # ── query with memory (streaming) ─────────────────────────────────────────

    def query_stream(self, question: str) -> Generator:
        if not self.vectorstores:
            raise ValueError("No documents have been uploaded yet.")
        if not self.active_docs:
            raise ValueError("No documents are selected. Enable at least one document in the sidebar.")

        # Condense follow-ups into standalone queries so retrieval works correctly
        search_query = self._condense_question(question)
        context, sources = self._retrieve_with_sources(search_query)

        if not context:
            raise ValueError("Could not retrieve relevant content from the selected documents.")

        chain = MEMORY_PROMPT | self.llm | StrOutputParser()

        full_answer = ""
        for chunk in chain.stream({
            "context": context,
            "question": question,       # use original question for the LLM answer
            "history": self.chat_history[-8:],
        }):
            full_answer += chunk
            yield chunk

        self.chat_history.append(HumanMessage(content=question))
        self.chat_history.append(AIMessage(content=full_answer))

        # Signal completion with source attribution
        yield {"sources": sources}

    # ── summarize (streaming) ─────────────────────────────────────────────────

    def summarize_stream(self, filename: str) -> Generator[str, None, None]:
        vs = self.vectorstores.get(filename)
        if not vs:
            raise ValueError(f"Document '{filename}' not loaded. Re-activate it from History first.")
        docs = vs.similarity_search("summary overview introduction", k=6)
        context = "\n\n".join(doc.page_content for doc in docs)
        chain = SUMMARY_PROMPT | self.llm | StrOutputParser()
        for chunk in chain.stream({"context": context}):
            yield chunk

    # ── clear ─────────────────────────────────────────────────────────────────

    def clear(self):
        self.vectorstores = {}
        self.session_docs = []
        self.history_docs = []
        self.active_docs = []
        self.chat_history = []
        if os.path.exists(VECTORSTORE_DIR):
            shutil.rmtree(VECTORSTORE_DIR)
        if os.path.exists(DOCS_FILE):
            os.remove(DOCS_FILE)

    def remove_document(self, filename: str):
        if filename in self.vectorstores:
            del self.vectorstores[filename]
        if filename in self.session_docs:
            self.session_docs.remove(filename)
        if filename in self.history_docs:
            self.history_docs.remove(filename)
        if filename in self.active_docs:
            self.active_docs.remove(filename)
        path = os.path.join(VECTORSTORE_DIR, filename)
        if os.path.exists(path):
            shutil.rmtree(path)
        self._save_state()
