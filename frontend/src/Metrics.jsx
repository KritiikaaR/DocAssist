import { useCallback, useEffect, useState } from "react";
import "./Metrics.css";
import { LatencyChart, MiniSteps, StepBreakdown } from "./charts.jsx";
import { fmtMs, fmtPct, fmtTime, fmtUsd } from "./format.js";

const API = "http://localhost:5000";
const REFRESH_MS = 5000;

// Unset in production unless explicitly configured for a given deployment —
// see the "Observability" section of the README for why /metrics is gated.
const JAEGER_URL = import.meta.env.VITE_JAEGER_URL;

// There is deliberately no VITE_METRICS_ADMIN_TOKEN build-time env var: Vite
// inlines import.meta.env.* into the shipped JS bundle, so a build-time token
// would be readable by anyone who opens devtools — the opposite of what it's
// for. Instead, a 401 from the backend prompts for the token at runtime (see
// TokenGate below), and it lives only in this component's React state — never
// written to localStorage/sessionStorage/a cookie — so it's gone as soon as
// the tab is closed or this page is navigated away from.

function IconBack(props) {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </svg>
  );
}

function IconRefresh(props) {
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" {...props}>
      <path d="M4 9a8 8 0 0 1 14-4.5M20 15a8 8 0 0 1-14 4.5" />
      <path d="M4 4v5h5M20 20v-5h-5" />
    </svg>
  );
}

function TraceLink({ traceId }) {
  if (!JAEGER_URL) return <span className="metrics-muted">—</span>;
  return (
    <a className="metrics-trace-link" href={`${JAEGER_URL}/trace/${traceId}`} target="_blank" rel="noreferrer">
      trace ↗
    </a>
  );
}

function TokenGate({ rejected, onSubmit }) {
  const [draft, setDraft] = useState("");
  return (
    <div className="metrics-card metrics-token-gate">
      <p className="metrics-error">
        {rejected
          ? "That token was rejected."
          : "This backend requires an admin token to view metrics."}
      </p>
      <form
        className="metrics-token-form"
        onSubmit={(e) => { e.preventDefault(); onSubmit(draft.trim()); }}
      >
        <input
          type="password"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Admin token"
          autoFocus
        />
        <button type="submit" disabled={!draft.trim()}>Unlock</button>
      </form>
    </div>
  );
}

function StatTile({ label, value, hint, danger }) {
  return (
    <div className="metrics-stat">
      <span className="metrics-stat-label">{label}</span>
      <span className={`metrics-stat-value${danger ? " danger" : ""}`}>{value}</span>
      {hint && <span className="metrics-stat-hint">{hint}</span>}
    </div>
  );
}

function RequestsTable({ rows }) {
  if (!rows.length) return <p className="metrics-muted">No requests yet.</p>;
  return (
    <div className="metrics-table-wrap">
      <table className="metrics-table">
        <thead>
          <tr>
            <th>Time</th>
            <th>Kind</th>
            <th>Question</th>
            <th className="num">Latency</th>
            <th>Steps</th>
            <th className="num">Tokens</th>
            <th className="num">Cost</th>
            <th className="num">Grounded</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.trace_id}>
              <td className="metrics-muted">{fmtTime(r.created_at)}</td>
              <td><span className="metrics-kind-badge">{r.kind}</span></td>
              <td className="metrics-q">{r.question || "—"}</td>
              <td className="num">{fmtMs(r.total_ms)}</td>
              <td><MiniSteps steps={r.steps} /></td>
              <td className="num">{r.input_tokens + r.output_tokens}</td>
              <td className="num">{fmtUsd(r.cost_usd)}</td>
              <td className="num">{fmtPct(r.groundedness)}</td>
              <td>
                <span className={`metrics-badge ${r.status}`} title={r.error || ""}>
                  {r.status === "ok" ? "✓ ok" : "✕ error"}
                </span>
              </td>
              <td><TraceLink traceId={r.trace_id} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Metrics({ onBack }) {
  const [summary, setSummary] = useState(null);
  const [rows, setRows] = useState([]);
  const [offline, setOffline] = useState(false);
  // 403: no METRICS_ADMIN_TOKEN configured on the backend at all, and this
  // request isn't from localhost — a token wouldn't help, only reconfiguring
  // the backend would, so there's nothing to prompt for.
  const [forbidden, setForbidden] = useState(false);
  // 401: the backend has a token configured and this request didn't present
  // the right one — prompt for it. `token` lives only in memory (see the
  // comment above) and is sent as a header on every subsequent request.
  const [needsToken, setNeedsToken] = useState(false);
  const [tokenRejected, setTokenRejected] = useState(false);
  const [token, setToken] = useState("");

  const authHeaders = useCallback(
    () => (token ? { "X-Metrics-Token": token } : {}),
    [token]
  );

  const refresh = useCallback(async () => {
    try {
      const headers = authHeaders();
      const [summaryRes, rowsRes] = await Promise.all([
        fetch(`${API}/metrics/summary`, { headers }),
        fetch(`${API}/metrics/requests`, { headers }),
      ]);
      if (summaryRes.status === 403) {
        setForbidden(true);
        setNeedsToken(false);
        return;
      }
      if (summaryRes.status === 401) {
        setNeedsToken(true);
        setTokenRejected(Boolean(token)); // had a token and it still failed
        setForbidden(false);
        return;
      }
      setForbidden(false);
      setNeedsToken(false);
      setSummary(await summaryRes.json());
      setRows(await rowsRes.json());
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, [authHeaders, token]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  async function resetMetrics() {
    await fetch(`${API}/metrics`, { method: "DELETE", headers: authHeaders() });
    refresh();
  }

  const blocked = forbidden || needsToken;

  return (
    <div className="metrics-page">
      <header className="metrics-header">
        <div className="metrics-header-left">
          <button className="back-btn" onClick={onBack} title="Back to mode selection">
            <IconBack /> Back
          </button>
          <div>
            <h1>Metrics</h1>
            <p>Where every request spends its time, tokens, and cost</p>
          </div>
        </div>
        <button className="metrics-reset-btn" onClick={resetMetrics} title="Clear stored metrics">
          <IconRefresh /> Reset metrics
        </button>
      </header>

      <div className="metrics-body">
        {forbidden && (
          <p className="metrics-error">
            Metrics are local-only in this environment. Set METRICS_ADMIN_TOKEN on the backend to
            view them remotely.
          </p>
        )}
        {needsToken && (
          <TokenGate rejected={tokenRejected} onSubmit={setToken} />
        )}
        {offline && !blocked && (
          <p className="metrics-error">Can't reach the backend. Is it running on port 5000?</p>
        )}

        {summary && !blocked && (
          <>
            <section className="metrics-stats">
              <StatTile label="Requests" value={summary.count} />
              <StatTile label="p50 latency" value={fmtMs(summary.p50_ms)} />
              <StatTile label="p95 latency" value={fmtMs(summary.p95_ms)} hint="slowest 5%" />
              <StatTile label="TTFT p50" value={fmtMs(summary.ttft_p50_ms)} hint="time to first token" />
              <StatTile label="TTFT p95" value={fmtMs(summary.ttft_p95_ms)} />
              <StatTile label="Cost / request" value={fmtUsd(summary.avg_cost_usd)} />
              <StatTile label="Avg tokens" value={Math.round(summary.avg_tokens)} />
              <StatTile label="Groundedness" value={fmtPct(summary.avg_groundedness)} hint="answer backed by context" />
              <StatTile
                label="Error rate"
                value={fmtPct(summary.error_rate)}
                danger={summary.error_rate > 0}
              />
            </section>

            <div className="metrics-grid-2">
              <section className="metrics-card">
                <h2>Where the time goes</h2>
                <p className="metrics-muted metrics-small">Average share of each pipeline step</p>
                <StepBreakdown stepAvg={summary.step_avg_ms} stepShare={summary.step_share} />
              </section>
              <section className="metrics-card">
                <h2>Latency per request</h2>
                <p className="metrics-muted metrics-small">Last {rows.length} requests · red dots are errors</p>
                <LatencyChart rows={rows} p95={summary.p95_ms} />
              </section>
            </div>
          </>
        )}

        {!blocked && (
          <section className="metrics-card">
            <h2>Recent requests</h2>
            <RequestsTable rows={rows} />
          </section>
        )}
      </div>
    </div>
  );
}
