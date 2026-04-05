import React, { useState, useEffect, useRef, useCallback } from "react";
import { Link } from "react-router-dom";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";
import {
  VERDICT_LABEL, pillClass, rowClass,
} from "../utils/verdictUtils";
import { relativeTime } from "../utils/timeUtils";

// ============================================================
// MessageHistory.jsx — View past message-check results
// ============================================================
// Route used: GET /api/message-checks/history
// ============================================================

// Returns a compact icon for how the message was submitted
function inputIcon(method) {
  if (method === "screenshot_ocr") return <span className="input-method-icon" title="Screenshot (OCR)">&#128247;</span>;
  if (method === "sms_text")       return <span className="input-method-icon" title="SMS text">&#128241;</span>;
  return null;
}

function MessageHistory() {
  const [checks, setChecks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [retryIn, setRetryIn]   = useState(0);   // countdown seconds
  const [filter, setFilter] = useState("all");

  // Guard against stale state updates from unmounted instances.
  // React StrictMode unmounts and remounts components in development,
  // which would otherwise fire useEffect twice and set state on the
  // already-unmounted first instance.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  // fetchHistory is stable across retries; useCallback prevents it
  // from being recreated on every render.
  const fetchHistory = useCallback(async () => {
    if (!mountedRef.current) return;
    setLoading(true);
    setError("");
    setIsRateLimited(false);

    const token = localStorage.getItem("token");
    if (!token) {
      if (mountedRef.current) { setError("You must log in first."); setLoading(false); }
      return;
    }

    try {
      const { data, response } = await authFetch("/message-checks/history");
      if (!mountedRef.current) return; // component unmounted while request was in-flight

      if (response.ok) {
        setChecks(data.data || []);
      } else if (response.status === 429) {
        // Rate limited — show a user-friendly message and start a retry countdown
        setIsRateLimited(true);
        startRetryCountdown(15);
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load history.");
      }
    } catch (err) {
      if (!mountedRef.current) return;
      console.error("[MessageHistory] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { fetchHistory(); }, [fetchHistory]);

  // Countdown timer shown on the retry button after a 429.
  // Automatically retries when it reaches zero.
  function startRetryCountdown(seconds) {
    setRetryIn(seconds);
    const interval = setInterval(() => {
      setRetryIn((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          if (mountedRef.current) fetchHistory();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
  }

  // Stats
  const total      = checks.length;
  const genuine    = checks.filter((c) => c.prediction_summary?.predicted_label === "genuine").length;
  const suspicious = checks.filter((c) => c.prediction_summary?.predicted_label === "suspicious").length;
  const fraud      = checks.filter((c) => c.prediction_summary?.predicted_label === "likely_fraudulent").length;
  const outOfScope = checks.filter((c) => c.prediction_summary?.predicted_label === "out_of_scope").length;

  // Apply filter
  const filtered = filter === "all"
    ? checks
    : checks.filter((c) => c.prediction_summary?.predicted_label === filter);

  return (
    <PageLayout
      title="Message History"
      subtitle="Audit log of all past MoMo message checks."
    >
      {/* Rate-limited — friendly message with auto-retry countdown */}
      {isRateLimited && !loading && (
        <div className="message-box warning history-rate-limit-box" role="alert" aria-live="polite">
          <span className="message-icon">&#9203;</span>
          <div>
            <strong>The server is busy &mdash; too many requests in quick succession.</strong>
            <p style={{ margin: "0.35rem 0 0.6rem", fontSize: "0.84rem" }}>
              Your history will reload automatically, or you can retry manually.
            </p>
            <button
              className="btn btn-outline history-retry-btn"
              onClick={fetchHistory}
              disabled={retryIn > 0}
            >
              {retryIn > 0 ? `Retrying in ${retryIn}s…` : "Try again"}
            </button>
          </div>
        </div>
      )}

      {/* General error */}
      {error && (
        <div className="message-box error" role="alert" aria-live="assertive">
          <span className="message-icon">&#10060;</span>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading message history…</p>
        </div>
      )}

      {/* Empty */}
      {!loading && !error && !isRateLimited && checks.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">&#128232;</div>
          <p>No message checks yet.</p>
          <Link to="/check-message" className="btn btn-primary" style={{ marginTop: "1rem", display: "inline-flex" }}>
            &#128737;&#65039; Check Your First Message
          </Link>
        </div>
      )}

      {/* ── Stat strip ── */}
      {!loading && checks.length > 0 && (
        <div className="history-stat-strip">
          <div className="history-stat">
            <span className="history-stat-value">{total}</span>
            <span className="history-stat-label">Total Checks</span>
          </div>
          <div className="history-stat history-stat--genuine">
            <span className="history-stat-value">{genuine}</span>
            <span className="history-stat-label">Verified</span>
          </div>
          <div className="history-stat history-stat--suspicious">
            <span className="history-stat-value">{suspicious}</span>
            <span className="history-stat-label">Needs Review</span>
          </div>
          <div className="history-stat history-stat--fraud">
            <span className="history-stat-value">{fraud}</span>
            <span className="history-stat-label">Potential Fraud</span>
          </div>
          {outOfScope > 0 && (
            <div className="history-stat history-stat--oos">
              <span className="history-stat-value">{outOfScope}</span>
              <span className="history-stat-label">Not Analysed</span>
            </div>
          )}
        </div>
      )}

      {/* Filter pills */}
      {!loading && checks.length > 0 && (
        <div className="filter-pills">
          {[
            { key: "all",               label: "All",             count: total },
            { key: "genuine",           label: "Verified",        count: genuine },
            { key: "suspicious",        label: "Needs Review",    count: suspicious },
            { key: "likely_fraudulent", label: "Potential Fraud", count: fraud },
          ].map(({ key, label, count }) => (
            <button
              key={key}
              className={`filter-pill ${filter === key ? "active" : ""}`}
              onClick={() => setFilter(key)}
            >
              {label} ({count})
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      {filtered.length > 0 && (
        <div className="table-container">
          <span className="sr-only" aria-live="polite" aria-atomic="true">
            {filtered.length} message{filtered.length !== 1 ? "s" : ""} shown
          </span>
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Date &amp; Time</th>
                <th scope="col">Sender</th>
                <th scope="col">Amount</th>
                <th scope="col">Verdict</th>
                <th scope="col">Confidence</th>
                <th scope="col" aria-label="Actions"></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const mc = item.message_check;
                const ps = item.prediction_summary;
                const label = ps?.predicted_label;
                const sender = mc.sender_name || mc.counterparty_name;
                const senderNum = mc.sender_number || mc.counterparty_number;
                const noVerdictYet = !ps;
                const confidence = ps?.confidence_score;

                return (
                  <tr key={mc.id} className={rowClass(label)}>
                    {/* Date */}
                    <td style={{ whiteSpace: "nowrap" }} title={relativeTime(mc.created_at).full}>
                      {relativeTime(mc.created_at).label}
                    </td>

                    {/* Sender — show number as secondary if name is absent */}
                    <td>
                      {sender ? (
                        <span className="history-sender">
                          {inputIcon(mc.input_method)}
                          <span>{sender}</span>
                          {senderNum && <span className="history-sender-num">{senderNum}</span>}
                        </span>
                      ) : senderNum ? (
                        <span className="history-sender">
                          {inputIcon(mc.input_method)}
                          <span>{senderNum}</span>
                        </span>
                      ) : (
                        <span className="history-unknown">
                          {inputIcon(mc.input_method)}
                          <span className="history-unknown-text">Sender unavailable</span>
                        </span>
                      )}
                    </td>

                    {/* Amount */}
                    <td className="amount-cell">
                      {mc.amount != null
                        ? <span className="history-amount">{mc.currency || "GHS"} {Number(mc.amount).toLocaleString()}</span>
                        : <span className="history-null">—</span>
                      }
                    </td>

                    {/* Verdict */}
                    <td>
                      {noVerdictYet ? (
                        <span className="status-pill info" title="This message was not eligible for fraud analysis">Not Analysed</span>
                      ) : (
                        <span className={`status-pill ${pillClass(label)}`}>
                          {VERDICT_LABEL[label] || (label || "").replace(/_/g, " ")}
                        </span>
                      )}
                    </td>

                    {/* Confidence */}
                    <td className="history-confidence-cell">
                      {confidence != null && label !== "out_of_scope" ? (
                        <span className="history-confidence">{Math.round(confidence * 100)}%</span>
                      ) : (
                        <span className="history-null">—</span>
                      )}
                    </td>

                    {/* Action */}
                    <td>
                      <Link
                        to={`/message-history/${mc.id}`}
                        className="btn btn-outline btn-view"
                        aria-label={`View details for check from ${sender || senderNum || relativeTime(mc.created_at).label}`}
                      >
                        View Details
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* No matches for current filter */}
      {!loading && checks.length > 0 && filtered.length === 0 && (
        <div className="empty-state">
          <p>No messages match this filter.</p>
        </div>
      )}
    </PageLayout>
  );
}

export default MessageHistory;

