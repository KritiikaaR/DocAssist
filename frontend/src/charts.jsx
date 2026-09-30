import { useEffect, useRef, useState } from "react";
import { STEPS, STEP_LABELS, stepVar, fmtMs, fmtPct, fmtTime } from "./format.js";

function useWidth() {
  const ref = useRef(null);
  const [width, setWidth] = useState(600);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(260, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** One 100%-stacked bar showing where the average request spends its time. */
export function StepBreakdown({ stepAvg, stepShare }) {
  const [hover, setHover] = useState(null);
  const steps = STEPS.filter((s) => s in stepAvg);
  if (!steps.length) return <p className="metrics-muted">No requests yet.</p>;

  return (
    <div className="metrics-breakdown">
      <div className="metrics-stack" role="img" aria-label="Average time share by pipeline step">
        {steps.map((s) => (
          <div
            key={s}
            className="metrics-stack-seg"
            style={{ flexGrow: Math.max(stepShare[s], 0.004), background: stepVar(s) }}
            onMouseEnter={() => setHover(s)}
            onMouseLeave={() => setHover(null)}
          >
            {hover === s && (
              <div className="metrics-tooltip">
                <strong>{STEP_LABELS[s]}</strong>
                <span>{fmtMs(stepAvg[s])} avg · {fmtPct(stepShare[s])} of time</span>
              </div>
            )}
          </div>
        ))}
      </div>
      <ul className="metrics-legend">
        {steps.map((s) => (
          <li key={s}>
            <span className="metrics-swatch" style={{ background: stepVar(s) }} />
            <span className="metrics-legend-name">{STEP_LABELS[s]}</span>
            <span className="metrics-legend-val">{fmtPct(stepShare[s])}</span>
            <span className="metrics-muted">{fmtMs(stepAvg[s])}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Total latency per request, oldest to newest, with the p95 as a reference line. */
export function LatencyChart({ rows, p95 }) {
  const [ref, width] = useWidth();
  const [hoverIdx, setHoverIdx] = useState(null);
  const data = [...rows].reverse(); // API returns newest first
  const height = 200;
  const pad = { top: 14, right: 16, bottom: 26, left: 52 };

  if (data.length < 2) {
    return <div ref={ref} className="metrics-empty-chart metrics-muted">Ask a couple of questions to see the trend.</div>;
  }

  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;
  const maxY = Math.max(...data.map((d) => d.total_ms), p95) * 1.1;
  const x = (i) => pad.left + (i / (data.length - 1)) * innerW;
  const y = (v) => pad.top + innerH - (v / maxY) * innerH;
  const ticks = [0, maxY / 2, maxY].map((v) => Math.round(v));
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i)},${y(d.total_ms)}`).join(" ");

  const onMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - rect.left) / rect.width) * width;
    const i = Math.round(((px - pad.left) / innerW) * (data.length - 1));
    setHoverIdx(Math.min(data.length - 1, Math.max(0, i)));
  };
  const h = hoverIdx != null ? data[hoverIdx] : null;

  return (
    <div ref={ref} className="metrics-chart-wrap">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        onMouseMove={onMove}
        onMouseLeave={() => setHoverIdx(null)}
        role="img"
        aria-label="Latency per request"
      >
        {ticks.map((t) => (
          <g key={t}>
            <line className="metrics-grid" x1={pad.left} x2={width - pad.right} y1={y(t)} y2={y(t)} />
            <text className="metrics-axis" x={pad.left - 8} y={y(t) + 4} textAnchor="end">{fmtMs(t)}</text>
          </g>
        ))}
        <line className="metrics-ref-line" x1={pad.left} x2={width - pad.right} y1={y(p95)} y2={y(p95)} />
        <text className="metrics-axis metrics-ref-label" x={width - pad.right} y={y(p95) - 6} textAnchor="end">p95 {fmtMs(p95)}</text>

        <path d={path} className="metrics-line" />
        {data.map((d, i) =>
          d.status === "error" ? <circle key={d.trace_id} cx={x(i)} cy={y(d.total_ms)} r="5" className="metrics-err-dot" /> : null
        )}
        <text className="metrics-axis" x={pad.left} y={height - 6}>older</text>
        <text className="metrics-axis" x={width - pad.right} y={height - 6} textAnchor="end">newest</text>

        {h && (
          <g>
            <line className="metrics-crosshair" x1={x(hoverIdx)} x2={x(hoverIdx)} y1={pad.top} y2={pad.top + innerH} />
            <circle cx={x(hoverIdx)} cy={y(h.total_ms)} r="5" className="metrics-hover-dot" />
          </g>
        )}
      </svg>
      {h && (
        <div
          className="metrics-tooltip metrics-tooltip-floating"
          style={{ left: `${(x(hoverIdx) / width) * 100}%`, top: 0 }}
        >
          <strong>{fmtMs(h.total_ms)}</strong>
          <span>{fmtTime(h.created_at)} · {h.status}</span>
          {h.question && <span className="metrics-tooltip-q">{h.question}</span>}
        </div>
      )}
    </div>
  );
}

/** Tiny stacked bar used inside each table row. Widths are relative to that row's total. */
export function MiniSteps({ steps }) {
  if (!steps?.length) return <span className="metrics-muted">—</span>;
  const total = steps.reduce((a, s) => a + s.ms, 0) || 1;
  const title = steps.map((s) => `${STEP_LABELS[s.name] || s.name}: ${fmtMs(s.ms)}`).join("\n");
  return (
    <div className="metrics-mini-stack" title={title}>
      {steps.map((s) => (
        <div key={s.name} style={{ flexGrow: Math.max(s.ms / total, 0.01), background: stepVar(s.name) }} />
      ))}
    </div>
  );
}
