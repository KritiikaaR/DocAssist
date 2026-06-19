import { useState, useEffect, useRef } from "react";

const API = "http://localhost:5000";

function IconBack(props) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  );
}

function IconUpload(props) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 16V4M7 9l5-5 5 5M5 20h14" />
    </svg>
  );
}

function IconCheck(props) {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M5 12l4 4 10-10" />
    </svg>
  );
}

export default function QuizMode({ onBack }) {
  const [screen, setScreen] = useState("setup"); // "setup" | "quiz" | "results"

  // setup state
  const [sessionDocs, setSessionDocs] = useState([]);
  const [selectedDocs, setSelectedDocs] = useState([]);
  const [difficulty, setDifficulty] = useState("medium");
  const [questionTypes, setQuestionTypes] = useState(["multiple_choice", "true_false"]);
  const [numQuestions, setNumQuestions] = useState(5);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileRef = useRef(null);

  // quiz-taking state
  const [questions, setQuestions] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [selectedOption, setSelectedOption] = useState(null);

  useEffect(() => {
    fetch(`${API}/documents`)
      .then((res) => res.json())
      .then((data) => setSessionDocs(data.session || []))
      .catch(() => {});
  }, []);

  function toggleDoc(name) {
    setSelectedDocs((prev) => (prev.includes(name) ? prev.filter((d) => d !== name) : [...prev, name]));
  }

  function toggleType(type) {
    setQuestionTypes((prev) => (prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]));
  }

  async function handleUpload(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "txt"].includes(ext)) {
      setError("Only PDF and TXT files are supported.");
      return;
    }
    setUploading(true);
    setError("");
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Upload failed.");
      setSessionDocs((prev) => (prev.includes(data.filename) ? prev : [...prev, data.filename]));
      setSelectedDocs((prev) => (prev.includes(data.filename) ? prev : [...prev, data.filename]));
    } catch (e) {
      setError(e.message || "Could not upload file.");
    } finally {
      setUploading(false);
    }
  }

  async function generateQuiz() {
    if (selectedDocs.length === 0) {
      setError("Select at least one document.");
      return;
    }
    if (questionTypes.length === 0) {
      setError("Select at least one question type.");
      return;
    }
    setError("");
    setGenerating(true);
    try {
      const res = await fetch(`${API}/quiz/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filenames: selectedDocs,
          difficulty,
          question_types: questionTypes,
          num_questions: numQuestions,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to generate quiz.");
      if (!data.questions || data.questions.length === 0) throw new Error("No questions were generated.");
      setQuestions(data.questions);
      setAnswers({});
      setCurrentIndex(0);
      setSelectedOption(null);
      setScreen("quiz");
    } catch (e) {
      setError(e.message || "Could not generate quiz.");
    } finally {
      setGenerating(false);
    }
  }

  function nextQuestion() {
    const q = questions[currentIndex];
    if (selectedOption == null) return;
    const updatedAnswers = { ...answers, [q.id]: selectedOption };
    setAnswers(updatedAnswers);
    setSelectedOption(null);
    if (currentIndex + 1 < questions.length) {
      setCurrentIndex((i) => i + 1);
    } else {
      setScreen("results");
    }
  }

  function retakeQuiz() {
    setScreen("setup");
    setQuestions([]);
    setAnswers({});
    setCurrentIndex(0);
    setSelectedOption(null);
    setError("");
  }

  const score = questions.reduce((acc, q) => acc + (answers[q.id] === q.correct_answer ? 1 : 0), 0);

  // ── Quiz-taking screen ──
  if (screen === "quiz" && questions.length > 0) {
    const q = questions[currentIndex];
    const progressPct = ((currentIndex + 1) / questions.length) * 100;
    return (
      <div className="quiz-mode">
        <button className="back-btn" onClick={onBack} title="Back to mode selection">
          <IconBack /> Back
        </button>

        <div className="quiz-taking">
          <div className="quiz-progress-label">Question {currentIndex + 1} of {questions.length}</div>
          <div className="quiz-progress-bar">
            <div className="quiz-progress-fill" style={{ width: `${progressPct}%` }} />
          </div>

          <div className="quiz-question-card">
            <h2 className="quiz-question-text">{q.question}</h2>

            <div className="quiz-options">
              {q.type === "multiple_choice" &&
                (q.options || []).map((opt, i) => (
                  <button
                    key={i}
                    className={`quiz-option${selectedOption === opt ? " selected" : ""}`}
                    onClick={() => setSelectedOption(opt)}
                  >
                    {opt}
                  </button>
                ))}
              {q.type === "true_false" &&
                ["true", "false"].map((opt) => (
                  <button
                    key={opt}
                    className={`quiz-option${selectedOption === opt ? " selected" : ""}`}
                    onClick={() => setSelectedOption(opt)}
                  >
                    {opt === "true" ? "True" : "False"}
                  </button>
                ))}
            </div>
          </div>

          <button className="quiz-next-btn" onClick={nextQuestion} disabled={selectedOption == null}>
            {currentIndex + 1 < questions.length ? "Next" : "See Results"}
          </button>
        </div>
      </div>
    );
  }

  // ── Results screen ──
  if (screen === "results") {
    return (
      <div className="quiz-mode">
        <button className="back-btn" onClick={onBack} title="Back to mode selection">
          <IconBack /> Back
        </button>

        <div className="quiz-results">
          <div className="quiz-score">{score}/{questions.length} correct</div>

          <div className="quiz-review-list">
            {questions.map((q, i) => {
              const userAnswer = answers[q.id];
              const isCorrect = userAnswer === q.correct_answer;
              return (
                <div key={q.id} className={`quiz-review-item ${isCorrect ? "correct" : "incorrect"}`}>
                  <div className="quiz-review-question">{i + 1}. {q.question}</div>
                  <div className="quiz-review-answer">
                    Your answer: <strong>{userAnswer ?? "—"}</strong>
                  </div>
                  {!isCorrect && (
                    <div className="quiz-review-answer">
                      Correct answer: <strong>{q.correct_answer}</strong>
                    </div>
                  )}
                  {q.explanation && <div className="quiz-review-explanation">{q.explanation}</div>}
                </div>
              );
            })}
          </div>

          <button className="retake-btn" onClick={retakeQuiz}>Retake Quiz</button>
        </div>
      </div>
    );
  }

  // ── Setup screen (default) ──
  return (
    <div className="quiz-mode">
      <button className="back-btn" onClick={onBack} title="Back to mode selection">
        <IconBack /> Back
      </button>

      <div className="quiz-setup">
        <div>
          <h1 className="quiz-setup-title">Set up your quiz</h1>
          <p className="quiz-setup-subtitle">Pick documents, difficulty, and question types.</p>
        </div>

        {error && <div className="quiz-error">{error}</div>}

        <div className="quiz-setup-columns">
          <div className="quiz-setup-col">
            <div className="quiz-setup-section">
              <h3 className="quiz-setup-label">Documents</h3>

              <div
                className={`drop-zone${dragOver ? " drag-active" : ""}${uploading ? " uploading" : ""}`}
                onClick={() => !uploading && fileRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); handleUpload(e.dataTransfer.files[0]); }}
              >
                <input ref={fileRef} type="file" accept=".pdf,.txt" style={{ display: "none" }}
                  onChange={(e) => { handleUpload(e.target.files[0]); e.target.value = ""; }} />
                <div className="drop-icon"><IconUpload /></div>
                <p>{uploading ? "Processing..." : (<>Drop PDF or<br /><strong>click to upload</strong></>)}</p>
              </div>

              {sessionDocs.length === 0 ? (
                <p className="no-docs">No documents yet — upload one above to get started.</p>
              ) : (
                <div className="quiz-doc-list">
                  {sessionDocs.map((d) => (
                    <label key={d} className={`quiz-doc-item${selectedDocs.includes(d) ? " checked" : ""}`}>
                      <input type="checkbox" checked={selectedDocs.includes(d)} onChange={() => toggleDoc(d)} />
                      <span className="quiz-checkbox"><IconCheck /></span>
                      <span className="doc-name" title={d}>{d}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="quiz-setup-col">
            <div className="quiz-setup-section">
              <h3 className="quiz-setup-label">Difficulty</h3>
              <div className="quiz-difficulty-group">
                {["easy", "medium", "hard"].map((level) => (
                  <button
                    key={level}
                    className={`quiz-difficulty-btn${difficulty === level ? " active" : ""}`}
                    onClick={() => setDifficulty(level)}
                  >
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            <div className="quiz-setup-section">
              <h3 className="quiz-setup-label">Question types</h3>
              <div className="quiz-type-group">
                <label className={`quiz-type-item${questionTypes.includes("multiple_choice") ? " checked" : ""}`}>
                  <input
                    type="checkbox"
                    checked={questionTypes.includes("multiple_choice")}
                    onChange={() => toggleType("multiple_choice")}
                  />
                  <span className="quiz-checkbox"><IconCheck /></span>
                  Multiple Choice
                </label>
                <label className={`quiz-type-item${questionTypes.includes("true_false") ? " checked" : ""}`}>
                  <input
                    type="checkbox"
                    checked={questionTypes.includes("true_false")}
                    onChange={() => toggleType("true_false")}
                  />
                  <span className="quiz-checkbox"><IconCheck /></span>
                  True / False
                </label>
              </div>
            </div>

            <div className="quiz-setup-section">
              <h3 className="quiz-setup-label">Number of questions: {numQuestions}</h3>
              <input
                type="range"
                min={3}
                max={10}
                value={numQuestions}
                onChange={(e) => setNumQuestions(Number(e.target.value))}
                className="quiz-slider"
              />
              <div className="quiz-slider-labels"><span>3</span><span>10</span></div>
            </div>

            <button className="generate-quiz-btn" onClick={generateQuiz} disabled={generating || selectedDocs.length === 0}>
              {generating ? "Generating..." : "Generate Quiz"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
