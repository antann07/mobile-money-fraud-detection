import React, { useState, useEffect } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";
import {
  VERDICT_LABEL, VERDICT_HEADLINE, REVIEW_STATUS_LABEL, RISK_ITEMS,
  pillClass, verdictIcon, verdictClass, riskColor, riskLabel,
  splitExplanation,
} from "../utils/verdictUtils";

// ============================================================
// ReviewDetail.jsx — Admin detail + review form for a flagged check
// ============================================================
// Routes used:
//   GET  /api/reviews/:message_check_id
//   POST /api/reviews/:message_check_id
// ============================================================

function ReviewDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [check, setCheck] = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [existingReview, setExistingReview] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Review form state
  const [reviewerLabel, setReviewerLabel] = useState("");
  const [reviewStatus, setReviewStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState("");
  const [saveError, setSaveError] = useState("");

  useEffect(() => {
    // Reset all state when navigating to a different review
    setCheck(null);
    setPrediction(null);
    setExistingReview(null);
    setLoading(true);
    setError("");
    setReviewerLabel("");
    setReviewStatus("");
    setNotes("");
    setSaveMsg("");
    setSaveError("");
    fetchDetail();
  }, [id]);

  async function fetchDetail() {
    try {
      const { data, response } = await authFetch(`/api/reviews/${id}`);
      if (response.ok) {
        setCheck(data.data?.message_check || null);
        setPrediction(data.data?.prediction || null);
        const rev = data.data?.review || null;
        setExistingReview(rev);
        // Pre-fill form if a review already exists
        if (rev) {
          setReviewerLabel(rev.reviewer_label || "");
          setReviewStatus(rev.review_status || "");
          setNotes(rev.notes || "");
        }
      } else if (response.status === 403) {
        setError("Access denied. Admin privileges required.");
      } else if (response.status === 404) {
        setError("Message check not found.");
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load review detail.");
      }
    } catch (err) {
      console.error("[ReviewDetail] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setSaveMsg("");
    setSaveError("");

    if (!reviewerLabel) { setSaveError("Please select a reviewer label."); return; }
    if (!reviewStatus)  { setSaveError("Please select a review status."); return; }

    setSaving(true);
    try {
      const { data, response } = await authFetch(`/api/reviews/${id}`, "POST", {
        reviewer_label: reviewerLabel,
        review_status: reviewStatus,
        notes: notes.trim() || null,
      });

      if (response.ok) {
        setSaveMsg(data.message || "Review saved successfully.");
        setExistingReview(data.data || null);
      } else {
        setSaveError(data.errors?.join(" ") || "Failed to save review.");
      }
    } catch (err) {
      console.error("[ReviewDetail] Save failed:", err);
      setSaveError("Could not reach the server.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <PageLayout
      title={`Review Check #${id}`}
      subtitle="Review this flagged message and record your decision."
    >
      {/* Back link */}
      <Link to="/review-queue" className="back-link">
        ← Back to Review Queue
      </Link>

      {/* Error */}
      {error && (
        <div className="message-box error" style={{ marginTop: "0.5rem" }}>
          <span className="message-icon">❌</span>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading review detail…</p>
        </div>
      )}

      {/* Phase-10: handle edge case where load succeeded but check is null */}
      {!loading && !error && !check && (
        <div className="message-box warning">
          <span className="message-icon">⚠️</span>
          No data available for this check. It may have been deleted or not yet flagged.
        </div>
      )}

      {/* ── Content ── */}
      {!loading && !error && check && (
        <>
          {/* ── Prediction verdict card ── */}
          {prediction && (
            <div className={`result-card ${verdictClass(prediction.predicted_label)}`}>
              <div className="verdict-banner">
                <span className="verdict-icon">{verdictIcon(prediction.predicted_label)}</span>
                <div className="verdict-text">
                  <span className={`status-pill ${pillClass(prediction.predicted_label)}`}>
                    {VERDICT_LABEL[prediction.predicted_label] || (prediction.predicted_label || "").replace("_", " ")}
                  </span>
                  <p className="verdict-headline">{VERDICT_HEADLINE[prediction.predicted_label] || "Verdict could not be determined"}</p>
                </div>
                <div className="verdict-score">
                  <span className="verdict-pct">
                    {Math.round((prediction.confidence_score || 0) * 100)}%
                  </span>
                  <span className="verdict-sub">confidence</span>
                </div>
              </div>

              {/* Explanation — split into short sentence chunks */}
              {prediction.explanation && (() => {
                const chunks = splitExplanation(prediction.explanation, prediction.predicted_label);
                const boxType = prediction.predicted_label === "genuine" ? "success"
                  : prediction.predicted_label === "suspicious" ? "warning" : "error";
                return (
                  <div className={`message-box ${boxType}`} style={{ marginTop: "1rem" }}>
                    <div>
                      {chunks.length <= 1
                        ? <span>{chunks[0]}</span>
                        : <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                            {chunks.map((s, i) => <li key={i} style={{ marginBottom: "0.2rem" }}>{s}</li>)}
                          </ul>
                      }
                    </div>
                  </div>
                );
              })()}

              {/* Risk score breakdown */}
              <h4 className="section-title" style={{ marginTop: "1.25rem" }}>Risk Breakdown</h4>
              <div className="risk-grid">
                {RISK_ITEMS.map((s) => (
                  <div key={s.key} className={`risk-item ${riskColor(prediction[s.key])}`}>
                    <span className="risk-label">{s.label}</span>
                    <span className="risk-value">
                      {riskLabel(prediction[s.key])}
                      {prediction[s.key] != null && (
                        <span className="risk-detail">({Math.round(prediction[s.key] * 100)}%)</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Raw SMS ── */}
          <div className="form-card" style={{ marginTop: "1.5rem" }}>
            <h3>Original Message</h3>
            <pre className="raw-text-block">
              {check.raw_text || check.extracted_text || "(no message text available)"}
            </pre>
          </div>

          {/* ── Extracted Fields — progressive disclosure ── */}
          <details className="tech-details" style={{ marginTop: "1.5rem" }}>
            <summary style={{ fontSize: "0.85rem", fontWeight: 600, color: "var(--color-slate-500)", cursor: "pointer", padding: "0.25rem 0" }}>
              Show parsed message fields
            </summary>
            <div className="form-card" style={{ marginTop: "0.75rem" }}>
              <div className="table-container">
                <table className="data-table">
                  <tbody>
                    {[
                      ["Transaction Type",     check.transaction_type],
                      ["Direction",            check.direction],
                      ["MTN Transaction ID",   check.mtn_transaction_id],
                      ["Transaction Ref",      check.transaction_reference],
                      ["Date/Time",            check.transaction_datetime],
                      ["Counterparty",         check.counterparty_name || check.counterparty_number],
                      ["Amount",               check.amount != null ? `${check.currency || "GHS"} ${check.amount}` : null],
                      ["Fee",                  check.fee != null ? `${check.currency || "GHS"} ${check.fee}` : null],
                      ["Balance After",        check.balance_after != null ? `${check.currency || "GHS"} ${check.balance_after}` : null],
                      ["Available Balance",    check.available_balance != null ? `${check.currency || "GHS"} ${check.available_balance}` : null],
                    ].filter(([, value]) => value != null && value !== "" && value !== "—").map(([label, value]) => (
                      <tr key={label}>
                        <td className="detail-field-label extracted-label" style={{ textTransform: "none", letterSpacing: "normal", fontSize: "0.84rem", fontWeight: 600 }}>
                          {label}
                        </td>
                        <td>{value || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </details>

          {/* ── Existing review info ── */}
          {existingReview && existingReview.reviewed_at && (
            <div className="message-box info" style={{ marginTop: "1.5rem" }}>
              Reviewed {new Date(existingReview.reviewed_at).toLocaleDateString()} —{" "}
              <strong>{REVIEW_STATUS_LABEL[existingReview.review_status] || "Reviewed"}</strong>
              {existingReview.notes && (
                <span style={{ display: "block", marginTop: "0.25rem", fontSize: "0.85rem", color: "var(--color-slate-500)" }}>
                  {existingReview.notes}
                </span>
              )}
            </div>
          )}

          {/* ── Review Form ── */}
          <div className="form-card review-form" style={{ marginTop: "1.5rem" }}>
            <h3 id="review-form-heading">Your Decision</h3>
            <form onSubmit={handleSubmit} aria-labelledby="review-form-heading">
              {/* Reviewer Label */}
              <div className="form-group">
                <label htmlFor="reviewerLabel">Your Verdict</label>
                <span className="form-hint">What do you believe this message actually is?</span>
                <select
                  id="reviewerLabel"
                  value={reviewerLabel}
                  onChange={(e) => setReviewerLabel(e.target.value)}
                >
                  <option value="">— select —</option>
                  <option value="genuine">Verified — genuine MTN MoMo message</option>
                  <option value="suspicious">Needs further investigation</option>
                  <option value="likely_fraudulent">Fraudulent — not a genuine MoMo message</option>
                </select>
              </div>

              {/* Review Status */}
              <div className="form-group">
                <label htmlFor="reviewStatus">Review Decision</label>
                <span className="form-hint">What action should be taken?</span>
                <select
                  id="reviewStatus"
                  value={reviewStatus}
                  onChange={(e) => setReviewStatus(e.target.value)}
                >
                  <option value="">— select —</option>
                  <option value="pending">Keep pending — not yet decided</option>
                  <option value="confirmed_genuine">Confirmed genuine — mark as safe</option>
                  <option value="confirmed_fraud">Confirmed fraud — flag for action</option>
                  <option value="escalated">Escalate — requires senior review</option>
                </select>
              </div>

              {/* Notes */}
              <div className="form-group">
                <label htmlFor="reviewNotes">Notes (optional)</label>
                <textarea
                  id="reviewNotes"
                  className="form-textarea"
                  rows={3}
                  maxLength={2000}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Add context or reasoning for your review decision…"
                />
                <span className="form-hint">{notes.length}/2000 characters</span>
              </div>

              {/* Save feedback */}
              {saveError && (
                <div className="message-box error" role="alert" aria-live="assertive" style={{ marginBottom: "0.75rem" }}>
                  <span className="message-icon">❌</span>
                  {saveError}
                </div>
              )}
              {saveMsg && (
                <div className="message-box success" role="status" aria-live="polite" style={{ marginBottom: "0.75rem" }}>
                  <span className="message-icon">✅</span>
                  {saveMsg}
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary"
                disabled={saving}
                style={{ minWidth: "140px" }}
              >
                {saving ? "Saving…" : existingReview ? "Update Review" : "Submit Review"}
              </button>
            </form>
          </div>

          {/* Post-save next-action strip: prominent CTA so admin can triage fast */}
          {saveMsg && (
            <div className="review-next-bar">
              <p>✅ Review saved. Ready for the next item?</p>
              <Link to="/review-queue" className="btn btn-primary">
                Review Next →
              </Link>
              <button className="btn btn-outline" onClick={() => navigate(-1)}>
                Back
              </button>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}

export default ReviewDetail;
