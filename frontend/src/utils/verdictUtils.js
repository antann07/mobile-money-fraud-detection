// ============================================================
// verdictUtils.js — Shared verdict display helpers
// ============================================================
// Centralises all verdict-related labels, icons, CSS classes,
// and risk-score interpretation used across pages.
// Import from here instead of duplicating per-page.
// ============================================================

// ── Display labels (never show raw DB values to users) ─────
export const VERDICT_LABEL = {
  genuine:            "Verified",
  suspicious:         "Needs Review",
  likely_fraudulent:  "Potential Fraud",
  out_of_scope:       "Not Analysed",
};

export const VERDICT_HEADLINE = {
  genuine:            "This notification appears authentic",
  suspicious:         "This message could not be fully verified",
  likely_fraudulent:  "This message shows signs of fraud",
  out_of_scope:       "This message type is outside the fraud detection scope",
};

export const VERDICT_GUIDANCE = {
  genuine:
    "Matches expected MTN MoMo patterns. You can proceed normally." +
    "\nFor large transfers, always confirm your balance via *170# first.",
  suspicious:
    "Do not act on this message until you have confirmed it." +
    "\n\u2022 Do not call any numbers shown in the message" +
    "\n\u2022 Check your balance directly via *170#" +
    "\n\u2022 Contact MTN on 100 if you are uncertain",
  likely_fraudulent:
    "Do not act on this message." +
    "\n\u2022 Do not send money or share your PIN" +
    "\n\u2022 Do not call any numbers shown in the message" +
    "\n\u2022 Already responded? Contact MTN on 100 immediately",
  out_of_scope:
    "Only incoming credit alerts (transfers received, cash-in, deposits) are checked for fraud." +
    "\nThis message was saved to your history but no fraud score was calculated.",
};

// ── Risk score config ──────────────────────────────────────
export const RISK_ITEMS = [
  { label: "Message Format",      key: "format_risk_score" },
  { label: "Transaction Pattern",  key: "behavior_risk_score" },
  { label: "Balance Consistency",  key: "balance_consistency_score" },
  { label: "Sender History",       key: "sender_novelty_score" },
];

// ── Review status display labels ───────────────────────────
export const REVIEW_STATUS_LABEL = {
  pending:            "Pending",
  confirmed_genuine:  "Confirmed Genuine",
  confirmed_fraud:    "Confirmed Fraud",
  escalated:          "Escalated",
};

// ── Status pill CSS class ──────────────────────────────────
export function pillClass(label) {
  if (label === "genuine")            return "trusted";
  if (label === "suspicious")         return "review";
  if (label === "likely_fraudulent")  return "blocked";
  if (label === "out_of_scope")       return "info";
  return "info";
}

// ── Verdict icon ───────────────────────────────────────────
export function verdictIcon(label) {
  if (label === "genuine")            return "\u2705";
  if (label === "suspicious")         return "\u26a0\ufe0f";
  if (label === "likely_fraudulent")  return "\ud83d\udea8";
  if (label === "out_of_scope")       return "\u2139\ufe0f";
  return "\u2753";
}

// ── Result card CSS class ──────────────────────────────────
export function verdictClass(label) {
  if (label === "genuine")            return "verdict-genuine";
  if (label === "suspicious")         return "verdict-suspicious";
  if (label === "likely_fraudulent")  return "verdict-fraudulent";
  if (label === "out_of_scope")       return "verdict-info";
  return "verdict-unknown";
}

// ── Risk score → CSS class ─────────────────────────────────
export function riskColor(value) {
  if (value == null) return "";
  if (value <= 0.25) return "risk-low";
  if (value <= 0.55) return "risk-med";
  return "risk-high";
}

// ── Risk score → human-readable label ──────────────────────
export function riskLabel(value) {
  if (value == null) return "\u2014";
  if (value <= 0.25) return "Low";
  if (value <= 0.55) return "Moderate";
  return "High";
}

// ── Review-status pill CSS class ───────────────────────────
export function statusPillClass(status) {
  if (status === "confirmed_genuine") return "trusted";
  if (status === "confirmed_fraud")   return "blocked";
  if (status === "escalated")         return "review";
  return "info";
}

// ── Confidence bar colour helper ───────────────────────────
export function confidenceColor(label) {
  if (label === "genuine")            return "var(--color-success)";
  if (label === "suspicious")         return "var(--color-warning)";
  if (label === "likely_fraudulent")  return "var(--color-danger)";
  if (label === "out_of_scope")       return "var(--color-slate-400)";
  return "var(--color-slate-400)";
}

// ── Table row highlight class ──────────────────────────────
export function rowClass(label) {
  if (label === "likely_fraudulent") return "row-danger";
  if (label === "suspicious")        return "row-warning";
  return "";
}

// ── Key concern one-liner for suspicious / fraud verdicts ──
const CONCERN_MAP = {
  "Message Format":      "the message wording differs from standard MTN alerts",
  "Transaction Pattern": "this transaction is unusual for your account",
  "Balance Consistency": "the balance figures in this message don\u2019t add up",
  "Sender History":      "the sender is not in your transaction history",
};

export function keyConcern(prediction) {
  if (!prediction) return null;
  const label = prediction.predicted_label;
  if (label === "genuine") return null;

  // Only show when there is a clearly elevated risk factor
  const elevated = RISK_ITEMS
    .map(({ label: name, key }) => ({ name, value: prediction[key] ?? 0 }))
    .filter(s => s.value > 0.55)
    .sort((a, b) => b.value - a.value);

  if (elevated.length === 0) return null;

  const top = elevated[0];
  const reason = CONCERN_MAP[top.name] || "some elements of this message could not be verified";
  return `Key concern: ${reason}.`;
}

// ── Split a long explanation into scannable chunks ─────────
export function splitExplanation(text, label) {
  if (!text) return [];
  // Genuine explanations are short — keep them as a single block
  if (label === "genuine") return [text];
  // Split on sentence-ending punctuation followed by whitespace
  const parts = text
    .split(/(?<=[.!])\s+/)
    .map(s => s.trim())
    .filter(s => s.length > 0);
  // Cap at 4 items so the list stays scannable
  return parts.length > 4 ? parts.slice(0, 4) : parts;
}
