function IconSparkle(props) {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor" {...props}>
      <path d="M12 2l1.8 6.2L20 10l-6.2 1.8L12 18l-1.8-6.2L4 10l6.2-1.8L12 2z" />
    </svg>
  );
}

function IconChatBubble(props) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 12a8 8 0 1 1 3.2 6.4L4 20l1.1-3.8A8 8 0 0 1 4 12z" />
    </svg>
  );
}

function IconGradCap(props) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 4 2 9l10 5 10-5-10-5z" />
      <path d="M6 11.5V17c0 1 2.5 2.5 6 2.5s6-1.5 6-2.5v-5.5" />
      <path d="M21 9v5" />
    </svg>
  );
}

function IconGauge(props) {
  return (
    <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M12 4a9 9 0 1 0 9 9" />
      <path d="M12 13 17 7" />
      <path d="M12 13a1.4 1.4 0 1 0 0-2.8 1.4 1.4 0 0 0 0 2.8z" />
    </svg>
  );
}

// Off by default: a production build shouldn't advertise the dashboard unless
// this deployment explicitly wants it (it exposes questions users asked, and
// is gated server-side too — see the README's Observability section).
const METRICS_ENABLED = import.meta.env.VITE_METRICS_ENABLED === "true";

export default function Landing({ onSelectAssist, onSelectQuiz, onSelectMetrics }) {
  return (
    <div className="landing">
      <div className="landing-header">
        <div className="landing-logo-icon"><IconSparkle /></div>
        <h1 className="landing-title">DocAssist</h1>
        <p className="landing-subtitle">Choose how you'd like to work with your documents</p>
      </div>

      <div className="landing-cards">
        <button className="mode-card" onClick={onSelectAssist}>
          <div className="mode-card-icon"><IconChatBubble /></div>
          <h2>Assist</h2>
          <p>Ask questions, get summaries, and chat with your uploaded documents.</p>
        </button>

        <button className="mode-card" onClick={onSelectQuiz}>
          <div className="mode-card-icon"><IconGradCap /></div>
          <h2>Quiz Me</h2>
          <p>Test your knowledge with questions generated from your documents.</p>
        </button>

        {METRICS_ENABLED && (
          <button className="mode-card" onClick={onSelectMetrics}>
            <div className="mode-card-icon"><IconGauge /></div>
            <h2>Metrics</h2>
            <p>Latency, cost, and groundedness across recent requests.</p>
          </button>
        )}
      </div>
    </div>
  );
}
