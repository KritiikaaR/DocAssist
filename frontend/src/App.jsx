import { useState, useRef, useEffect } from "react";
import "./App.css";

const API = "http://localhost:5000";

const speechSupported = !!(window.SpeechRecognition || window.webkitSpeechRecognition);

function SourceItem({ filename, snippet }) {
  return (
    <details className="source-item">
      <summary className="source-toggle">
        <span className="source-chevron" />
        <span className="source-filename" title={filename}>{filename}</span>
      </summary>
      <p className="source-snippet">{snippet}</p>
    </details>
  );
}

function App() {
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Hello! I'm DocAssist. Upload any document (PDF or TXT) and ask me anything about it." }
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sessionDocs, setSessionDocs] = useState([]);
  const [historyDocs, setHistoryDocs] = useState([]);
  const [activeDocs, setActiveDocs] = useState([]);
  const [dragOver, setDragOver] = useState(false);
  const [suggestedQuestions, setSuggestedQuestions] = useState([]);
  const [listening, setListening] = useState(false);
  const bottomRef = useRef(null);
  const fileRef = useRef(null);
  const recognitionRef = useRef(null);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  useEffect(() => { fetchDocs(); }, []);

  async function fetchDocs() {
    try {
      const res = await fetch(`${API}/documents`);
      const data = await res.json();
      setSessionDocs(data.session || []);
      setHistoryDocs(data.history || []);
      setActiveDocs(data.active || []);
    } catch {}
  }

  async function handleUpload(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "txt"].includes(ext)) {
      addMessage("assistant", `Only PDF and TXT files are supported.`);
      return;
    }
    setUploading(true);
    addMessage("assistant", `Uploading "${file.name}"...`);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      const data = await res.json();
      if (res.ok) {
        addMessage("assistant", `"${file.name}" uploaded successfully! Ask me anything about it.`);
        if (data.suggested_questions && data.suggested_questions.length > 0) {
          setSuggestedQuestions(data.suggested_questions);
        }
        fetchDocs();
      } else {
        addMessage("assistant", `Upload failed: ${data.error}`);
      }
    } catch {
      addMessage("assistant", "Could not connect to backend. Is it running?");
    } finally {
      setUploading(false);
    }
  }

  function addMessage(role, text) {
    setMessages(prev => [...prev, { role, text }]);
  }

  async function activateFromHistory(filename) {
    addMessage("assistant", `Loading "${filename}" from history...`);
    try {
      const res = await fetch(`${API}/history/activate/${encodeURIComponent(filename)}`, { method: "POST" });
      const data = await res.json();
      if (res.ok) {
        addMessage("assistant", `"${filename}" is active. You can now ask questions about it.`);
        fetchDocs();
      } else {
        addMessage("assistant", `Could not load: ${data.error}`);
      }
    } catch {
      addMessage("assistant", "Could not reach backend.");
    }
  }

  // streaming send
  async function handleSend() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setSuggestedQuestions([]);
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);

    setMessages(prev => [...prev, { role: "assistant", text: "", streaming: true }]);

    try {
      const res = await fetch(`${API}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const json = JSON.parse(line.slice(6));
            if (json.error) {
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { role: "assistant", text: `${json.error}` };
                return updated;
              });
            } else if (json.token) {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, text: last.text + json.token };
                return updated;
              });
            } else if (json.done) {
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  ...updated[updated.length - 1],
                  streaming: false,
                  sources: json.sources || [],
                };
                return updated;
              });
            }
          } catch {}
        }
      }
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", text: "Could not reach the backend." };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  // streaming summarize
  async function handleSummarize(filename) {
    setLoading(true);
    setMessages(prev => [...prev, { role: "user", text: `Summarize: ${filename}` }]);
    setMessages(prev => [...prev, { role: "assistant", text: "", streaming: true }]);

    try {
      const res = await fetch(`${API}/summarize/${encodeURIComponent(filename)}`, { method: "POST" });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const json = JSON.parse(line.slice(6));
            if (json.token) {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, text: last.text + json.token };
                return updated;
              });
            } else if (json.done) {
              setMessages(prev => {
                const updated = [...prev];
                updated[updated.length - 1] = { ...updated[updated.length - 1], streaming: false };
                return updated;
              });
            }
          } catch {}
        }
      }
    } catch {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: "assistant", text: "Could not summarize." };
        return updated;
      });
    } finally {
      setLoading(false);
    }
  }

  async function toggleDoc(doc) {
    const newActive = activeDocs.includes(doc)
      ? activeDocs.filter(d => d !== doc)
      : [...activeDocs, doc];
    setActiveDocs(newActive);
    await fetch(`${API}/documents/active`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ docs: newActive }),
    });
  }

  function removeDoc(doc) {
    // Optimistic update — remove from all state arrays immediately
    setSessionDocs(prev => prev.filter(d => d !== doc));
    setHistoryDocs(prev => prev.filter(d => d !== doc));
    setActiveDocs(prev => prev.filter(d => d !== doc));
    fetch(`${API}/documents/${encodeURIComponent(doc)}`, { method: "DELETE" });
  }

  function handleClear() {
    // Update state first so the UI responds instantly
    setSessionDocs([]);
    setHistoryDocs([]);
    setActiveDocs([]);
    setMessages([{ role: "assistant", text: "All documents cleared. Upload a new document to get started." }]);
    fetch(`${API}/clear`, { method: "POST" });
  }

  function exportChat() {
    const win = window.open("", "_blank");
    win.document.write(`
      <html><head><title>DocAssist Chat Export</title>
      <style>
        body { font-family: Arial, sans-serif; padding: 32px; max-width: 800px; margin: 0 auto; color: #1a1a1a; }
        h1 { color: #00c9a7; margin-bottom: 24px; }
        .msg { margin-bottom: 20px; padding: 12px 16px; border-radius: 8px; }
        .user { background: #e8f4fd; border-left: 4px solid #0096c7; }
        .assistant { background: #f5f5f5; border-left: 4px solid #00c9a7; }
        .label { font-weight: bold; font-size: 12px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.05em; }
        hr { border: none; border-top: 1px solid #ddd; margin: 16px 0; }
      </style></head><body>
      <h1>DocAssist — Chat Export</h1>
      <p style="color:#666;margin-bottom:24px;">Exported on ${new Date().toLocaleString()}</p>
      ${messages.map(m => `
        <div class="msg ${m.role}">
          <div class="label">${m.role === "user" ? "You" : "DocAssist"}</div>
          <div>${m.text.replace(/\n/g, "<br/>")}</div>
        </div>
      `).join("<hr/>")}
      </body></html>
    `);
    win.document.close();
    win.print();
  }

  function handleKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function toggleListening() {
    if (listening) {
      recognitionRef.current?.stop();
      return;
    }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SR();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    const baseText = input;
    recognition.onresult = (e) => {
      console.log("Speech result:", e.results);
      const transcript = Array.from(e.results).map(r => r[0].transcript).join("");
      setInput(baseText ? `${baseText} ${transcript}` : transcript);
    };
    
    recognition.onend = () => setListening(false);
    recognition.onerror = (e) => {
      console.log("Speech error:", e.error);
      setListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="logo">
            <div className="logo-icon">⚕</div>
            <span className="logo-text">DocAssist<br /><em>RAG Assistant</em></span>
          </div>

          <div
            className={`drop-zone ${dragOver ? "drag-active" : ""} ${uploading ? "uploading" : ""}`}
            onClick={() => !uploading && fileRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files[0]); }}
          >
            <input ref={fileRef} type="file" accept=".pdf,.txt" style={{ display: "none" }}
              onChange={(e) => handleUpload(e.target.files[0])} />
            <div className="drop-icon">{uploading ? "⏳" : "📄"}</div>
            <p>{uploading ? "Processing..." : "Drop PDF or TXT\nor click to upload"}</p>
          </div>
        </div>

        <div className="doc-list">
          {/* Active session documents */}
          <h3>Documents</h3>
          {sessionDocs.length === 0 ? (
            <p className="no-docs">No documents this session</p>
          ) : (
            <ul>
              {sessionDocs.map((d) => (
                <li key={d} className={activeDocs.includes(d) ? "active-doc" : "inactive-doc"}>
                  <input type="checkbox" checked={activeDocs.includes(d)}
                    onChange={() => toggleDoc(d)} title="Include in search" />
                  <span className="doc-name" title={d}>{d}</span>
                  <div className="doc-actions">
                    <button className="summarize-btn" onClick={(e) => { e.stopPropagation(); handleSummarize(d); }} title="Summarize">∑</button>
                    <button className="delete-btn" onClick={(e) => { e.stopPropagation(); removeDoc(d); }} title="Remove">✕</button>
                  </div>
                </li>
              ))}
            </ul>
          )}

          {/* Previous session history */}
          {historyDocs.length > 0 && (
            <>
              <h3 className="history-heading">History</h3>
              <ul className="history-list">
                {historyDocs.map((d) => (
                  <li key={d} className="history-item">
                    <span className="doc-name history-name" title={d}>{d}</span>
                    <button
                      className="activate-btn"
                      onClick={() => activateFromHistory(d)}
                      title="Re-activate"
                    >↺</button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="sidebar-bottom">
          <button className="export-btn" onClick={exportChat} disabled={messages.length <= 1}>
            ↓ Export Chat
          </button>
          <button className="clear-btn" onClick={handleClear}>
            🗑 Clear All
          </button>
        </div>
      </aside>

      {/* Chat */}
      <main className="chat">
        <header className="chat-header">
          <h1>Ask about your documents</h1>
          <p>Powered by GPT-4o + LangChain + FAISS
            {activeDocs.length > 0 && <span className="active-hint"> · {activeDocs.length} doc{activeDocs.length > 1 ? "s" : ""} active</span>}
          </p>
        </header>

        <div className="messages">
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              <div className={`bubble ${m.streaming ? "streaming" : ""}`}>
                <p>{m.text}{m.streaming && <span className="cursor">▌</span>}</p>
                {!m.streaming && m.sources && m.sources.length > 0 && (
                  <div className="msg-sources">
                    <span className="sources-label">Sources</span>
                    {m.sources.map((s, si) => (
                      <SourceItem key={si} filename={s.filename} snippet={s.snippet} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && messages[messages.length - 1]?.role !== "assistant" && (
            <div className="msg assistant">
              <div className="bubble typing"><span /><span /><span /></div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {suggestedQuestions.length > 0 && (
          <div className="suggestions">
            <span className="suggestions-label">Try asking:</span>
            <div className="suggestions-list">
              {suggestedQuestions.map((q, i) => (
                <button key={i} className="suggestion-chip" onClick={() => {
                  setInput(q);
                  setSuggestedQuestions([]);
                }}>{q}</button>
              ))}
            </div>
          </div>
        )}

        <div className="input-row">
          <textarea value={input} onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your uploaded documents..."
            rows={1} disabled={loading} />
          {speechSupported && (
            <button
              className={`mic-btn${listening ? " listening" : ""}`}
              onClick={toggleListening}
              disabled={loading}
              title={listening ? "Stop listening" : "Voice input"}
            >🎤</button>
          )}
          <button onClick={handleSend} disabled={loading || !input.trim()} className="send-btn">
            {loading ? "..." : "↑"}
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;
