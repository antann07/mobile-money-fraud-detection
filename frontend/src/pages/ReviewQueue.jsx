import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { authFetch, refreshToken } from "../services/api";
import PageLayout from "../components/PageLayout";
import {
  VERDICT_LABEL, REVIEW_STATUS_LABEL,
  pillClass,
} from "../utils/verdictUtils";
import { relativeTime } from "../utils/timeUtils";

// ============================================================
// ReviewQueue.jsx — Admin review queue for flagged messages
// ============================================================
// Route used: GET /api/reviews/flagged
// ============================================================

// Sort: pending first → fraud before suspicious → newest first
// This surfaces the most urgent items at the top so admins can
// triage without scanning the entire list.
function sortByPriority(items) {
  const severity = { likely_fraudulent: 0, suspicious: 1, genuine: 2 };
  return [...items].sort((a, b) => {
    const aPending = !a.review_status || a.review_status === "pending";
    const bPending = !b.review_status || b.review_status === "pending";
    if (aPending !== bPending) return aPending ? -1 : 1;
    const sa = severity[a.predicted_label] ?? 3;
    const sb = severity[b.predicted_label] ?? 3;
    if (sa !== sb) return sa - sb;
    return new Date(b.created_at) - new Date(a.created_at);
  });
}

function ReviewQueue() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => { fetchFlagged(); }, []);

  async function fetchFlagged() {
    try {
      let { data, response } = await authFetch("/api/reviews/flagged");

      // If 403, the token role may be stale — try refreshing and retry once
      if (response.status === 403) {
        const refreshed = await refreshToken();
        if (refreshed) {
          ({ data, response } = await authFetch("/api/reviews/flagged"));
        }
      }

      if (response.ok) {
        setItems(data.data || []);
      } else if (response.status === 403) {
        // FIX: More helpful error — tells user to log out and back in
        setError("Access denied. Admin privileges required. Try logging out and logging back in to refresh your session.");
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load flagged checks.");
      }
    } catch (err) {
      console.error("[ReviewQueue] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  const total   = items.length;
  const fraud   = items.filter((i) => i.predicted_label === "likely_fraudulent").length;
  const pending = items.filter((i) => !i.review_status || i.review_status === "pending").length;
  const sorted  = sortByPriority(items);

  return (
    <PageLayout
      title="Review Queue"
      subtitle="Flagged messages awaiting admin review."
    >
      {/* Error */}
      {error && (
        <div className="message-box error" role="alert" aria-live="assertive">
          <span className="message-icon">❌</span>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading flagged checks…</p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && items.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🎉</div>
          <p>No flagged messages to review.</p>
          <p style={{ fontSize: "0.85rem", color: "var(--color-slate-400)" }}>
            Flagged messages that need review will appear here.
          </p>
        </div>
      )}

      {/* Summary line — one muted sentence, no color competition with the table */}
      {!loading && !error && items.length > 0 && (
        <p style={{ fontSize: "0.82rem", color: "var(--color-slate-400)", marginBottom: "1.5rem", letterSpacing: "0.01em" }}>
          {pending} pending &middot; {fraud} likely fraud &middot; {total - pending} reviewed
        </p>
      )}

      {/* Table */}
      {!loading && !error && items.length > 0 && (
        <div className="table-container">
          <table className="data-table review-table">
            <caption className="sr-only">
              Flagged message review queue — {items.length} item{items.length !== 1 ? "s" : ""},
              sorted by urgency (pending and high-severity first)
            </caption>
            <thead>
              <tr>
                {/* col-* classes provide min-width anchors — prevents 6-col collapse at tablet */}
                <th scope="col" className="col-verdict">Verdict</th>
                <th scope="col" className="col-date">Date</th>
                <th scope="col" className="col-party">Sender / Recipient</th>
                <th scope="col" className="col-amount">Amount</th>
                <th scope="col" className="col-status">Status</th>
                <th scope="col" className="col-action"></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((item) => {
                const isPending = !item.review_status || item.review_status === "pending";
                const isFraud   = item.predicted_label === "likely_fraudulent";
                // Party: prefer name; surface number as secondary line if it differs
                const party  = item.sender_name || item.counterparty_name || null;
                const number = item.counterparty_number && item.counterparty_number !== party
                  ? item.counterparty_number
                  : null;

                return (
                  <tr
                    key={item.message_check_id}
                    className={[
                      isFraud ? "row-danger" : "",
                      isFraud && isPending ? "row-urgent" : "",
                    ].filter(Boolean).join(" ") || undefined}
                  >
                    {/* Col 1 — Verdict pill (most important signal, scanned first) */}
                    <td>
                      <span className={`status-pill ${pillClass(item.predicted_label)}`}>
                        {VERDICT_LABEL[item.predicted_label] || (item.predicted_label || "").replace("_", " ")}
                      </span>
                    </td>

                    {/* Col 2 — Date (context, de-emphasised) */}
                    <td
                      style={{ whiteSpace: "nowrap", fontSize: "0.82rem", color: "var(--color-slate-500)" }}
                      title={relativeTime(item.created_at).full}
                    >
                      {relativeTime(item.created_at).label}
                    </td>

                    {/* Col 3 — Party: name prominent, number secondary */}
                    <td>
                      {party ? (
                        <>
                          <span style={{ fontWeight: 500 }}>{party}</span>
                          {number && (
                            <span style={{ display: "block", fontSize: "0.77rem", color: "var(--color-slate-400)", marginTop: "1px" }}>
                              {number}
                            </span>
                          )}
                        </>
                      ) : (
                        <span style={{ color: "var(--color-slate-400)" }}>—</span>
                      )}
                    </td>

                    {/* Col 4 — Amount: context signal, not primary */}
                    <td style={{ fontWeight: 500, color: "var(--color-slate-600)", fontVariantNumeric: "tabular-nums" }}>
                      {item.amount != null
                        ? `${item.currency || "GHS"} ${item.amount}`
                        : <span style={{ color: "var(--color-slate-300)" }}>—</span>}
                    </td>

                    {/* Col 5 — Status: dot indicator + text for pending, muted plain text for resolved */}
                    <td style={{ fontSize: "0.81rem", whiteSpace: "nowrap" }}>
                      {isPending ? (
                        <span style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem", color: "var(--color-slate-600)" }}>
                          <span style={{ display: "inline-block", width: "6px", height: "6px", borderRadius: "50%", background: "var(--color-warning)", flexShrink: 0 }} aria-hidden="true" />
                          Pending
                        </span>
                      ) : (
                        <span style={{ color: "var(--color-slate-400)" }}>
                          {REVIEW_STATUS_LABEL[item.review_status]}
                        </span>
                      )}
                    </td>

                    {/* Col 6 — Action: consistent outline style; label carries the intent */}
                    <td>
                      <Link
                        to={`/review-queue/${item.message_check_id}`}
                        className="btn btn-outline btn-view"
                        aria-label={isPending
                          ? `Review flagged message from ${item.sender_name || item.counterparty_name || "unknown"}`
                          : `View reviewed message from ${item.sender_name || item.counterparty_name || "unknown"}`}
                      >
                        {isPending ? "Review →" : "View →"}
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}

export default ReviewQueue;
