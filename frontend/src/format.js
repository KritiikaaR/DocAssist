// Fixed pipeline order: a step always gets the same color, no matter which
// steps are present in a given trace (condense_question only shows up on
// follow-up questions; quiz traces only ever have retrieve/generate).
export const STEPS = ["condense_question", "retrieve", "generate", "evaluate"];
export const STEP_LABELS = {
  condense_question: "Condense question",
  retrieve: "Retrieve",
  generate: "Generate",
  evaluate: "Evaluate",
};
export const stepVar = (name) => {
  const i = STEPS.indexOf(name);
  return i === -1 ? "var(--series-other)" : `var(--series-${i + 1})`;
};

export const fmtMs = (ms) => {
  if (ms == null) return "—";
  if (ms >= 1000) return `${(ms / 1000).toFixed(2)} s`;
  if (ms > 0 && ms < 10) return `${ms.toFixed(1)} ms`; // retrieval is fast; don't round it to 0
  return `${Math.round(ms)} ms`;
};
export const fmtUsd = (v) => {
  if (!v) return "$0";
  // Per-request costs are tiny, so show enough decimals to be meaningful.
  return v < 0.01 ? `$${v.toFixed(5)}` : `$${v.toFixed(2)}`;
};
export const fmtPct = (v) => (v == null ? "—" : `${Math.round(v * 100)}%`);
export const fmtTime = (epochSec) =>
  new Date(epochSec * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
