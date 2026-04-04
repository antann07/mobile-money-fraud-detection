import React, { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";
import {
  VERDICT_LABEL, VERDICT_HEADLINE, VERDICT_GUIDANCE, RISK_ITEMS,
  pillClass, verdictIcon, verdictClass, riskColor, riskLabel,
  confidenceColor, keyConcern, splitExplanation,
} from "../utils/verdictUtils";

// ============================================================
// MessageCheckDetail.jsx - Single message-check detail view
// ============================================================
// Route used: GET /api/message-checks/:id
// ============================================================

// Human-readable label for how the message was submitted
function inputMethodLabel(method) {
  if (method === "screenshot_ocr") return "Screenshot (OCR)";
  if (method === "sms_text")       return "SMS Text";
  return method || "Unknown";
}

// Render guidance lines: split on \n, format bullet lines as <li>
function renderGuidance(text) {
  if (!text) return null;
  const lines = text.split("\n").filter(Boolean);
  const intro = lines[0];
  const bullets = lines.slice(1).filter((l) => l.startsWith("\u2022") || l.startsWith("-"));
  const rest    = lines.slice(1).filter((l) => !l.startsWith("\u2022") && !l.startsWith("-"));

  return (
    <>
      <p style={{ margin: 0 }}>{intro}</p>
      {rest.map((l, i) => <p key={i} style={{ margin: "0.25rem 0 0" }}>{l}</p>)}
      {bullets.length > 0 && (
        <ul style={{ margin: "0.4rem 0 0", paddingLeft: "1.1rem" }}>
          {bullets.map((l, i) => (
            <li key={i} style={{ marginBottom: "0.2rem" }}>{l.replace(/^[\u2022\-]\s*/, "")}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function MessageCheckDetail() {
  const { id } = useParams();
  const [check, setCheck]         = useState(null);
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState("");

  useEffect(() => { fetchDetail(); }, [id]);

  async function fetchDetail() {
    const token = localStorage.getItem("token");
    if (!token) { setError("You must log in first."); setLoading(false); return; }

    try {
      const { data, response } = await authFetch(`/api/message-checks/${id}`);
      if (response.ok) {
        setCheck(data.data?.message_check || null);
        setPrediction(data.data?.prediction || null);
      } else if (response.status === 404) {
        setError("Message check not found.");
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load details.");
      }
    } catch (err) {
      console.error("[MessageCheckDetail] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PageLayout
      title="Message Check Details"
      subtitle={`Authenticity check \u00b7 Record #${id}`}
    >
      {/* Back link */}
      <Link to="/message-history" className="back-link">
        &larr; Back to History
      </Link>

      {/* Error */}
      {error && (
        <div className="message-box error" style={{ marginTop: "0.5rem" }}>
          <span className="message-icon">&#10060;</span>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading details&hellip;</p>
        </div>
      )}

      {/* Edge case: load succeeded but check is null */}
      {!loading && !error && !check && (
        <div className="message-box warning">
          <span className="message-icon">&#9888;&#65039;</span>
          No data available for this check. It may have been deleted.
        </div>
      )}

      {/* -- Content -- */}
      {!loading && !error && check && (
        <>
          {/* -- No prediction yet -- */}
          {!prediction && (
            <div className="message-box info">
              <span className="message-icon">&#8505;&#65039;</span>
              <span>
                <strong>Not Analysed</strong> &mdash; this message was saved to your history but was not checked for fraud.
                <br />
                <span className="pending-hint">Only incoming MTN MoMo credit alerts (payment received, transfer received, cash-in, deposit) are eligible for fraud analysis. You can paste the message text in the <Link to="/check-message">Verify Message</Link> tab to try again.</span>
              </span>
            </div>
          )}

          {/* -- Prediction verdict card -- */}
          {prediction && (
            <div className={`result-card ${verdictClass(prediction.predicted_label)}`}>

              {/* Verdict banner */}
              <div className="verdict-banner">
                <span className="verdict-icon">{verdictIcon(prediction.predicted_label)}</span>
                <div className="verdict-text">
                  <span className={`status-pill ${pillClass(prediction.predicted_label)}`}>
                    {VERDICT_LABEL[prediction.predicted_label] || (prediction.predicted_label || "").replace(/_/g, " ")}
                  </span>
                  <p className="verdict-headline">
                    {VERDICT_HEADLINE[prediction.predicted_label] || "Verdict could not be determined"}
                  </p>
                </div>
                {prediction.predicted_label !== "out_of_scope" && (
                  <div className="verdict-score">
                    <span className="verdict-pct">{Math.round((prediction.confidence_score || 0) * 100)}%</span>
                    <span className="verdict-sub">confidence</span>
                  </div>
                )}
              </div>

              {/* Confidence bar - hidden for out-of-scope */}
              {prediction.predicted_label !== "out_of_scope" && (
                <div className="confidence-track">
                  <div
                    className="confidence-fill"
                    style={{
                      width: `${Math.round((prediction.confidence_score || 0) * 100)}%`,
                      background: confidenceColor(prediction.predicted_label),
                    }}
                  />
                </div>
              )}

              {/* Action guidance */}
              {VERDICT_GUIDANCE[prediction.predicted_label] && (
                <div className="verdict-guidance">
                  {renderGuidance(VERDICT_GUIDANCE[prediction.predicted_label])}
                </div>
              )}

              {/* Key concern */}
              {keyConcern(prediction) && (
                <div className="key-concern" style={{ marginTop: "0.75rem" }}>
                  {keyConcern(prediction)}
                </div>
              )}

              {/* Explanation */}
              {prediction.explanation && (() => {
                const chunks = splitExplanation(prediction.explanation, prediction.predicted_label);
                const boxType = prediction.predicted_label === "genuine"     ? "success"
                              : prediction.predicted_label === "out_of_scope" ? "info"
                              : prediction.predicted_label === "suspicious"   ? "warning"
                              : "error";
                return (
                  <div className={`message-box ${boxType}`} style={{ marginTop: "0.75rem" }}>
                    <span className="message-icon">&#128161;</span>
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

              {/* Risk scores - hidden for out-of-scope */}
              {prediction.predicted_label !== "out_of_scope" && (
                <>
                  <h4 className="section-title detail-subsection-title">Risk Breakdown</h4>
                  <div className="risk-grid detail-risk-grid">
                    {RISK_ITEMS.map(({ label, key }) => (
                      <div className={`risk-item ${riskColor(prediction[key])}`} key={key}>
                        <span className="risk-label">{label}</span>
                        <span className="risk-value">
                          {riskLabel(prediction[key])}
                          {prediction[key] != null && (
                            <span className="risk-detail">({Math.round(prediction[key] * 100)}%)</span>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>

                  {/* ML model signal - collapsed under Analysis details */}
                  {prediction.ml_available && (
                    <details className="tech-details">
                      <summary>Analysis details</summary>
                      <div className={`ml-badge ${prediction.ml_agrees ? "ml-agrees" : "ml-differs"}`}>
                        <strong>Secondary check:</strong>{" "}
                        {prediction.ml_label === "genuine" ? "Looks legitimate" : "Looks suspicious"}
                        {prediction.ml_confidence > 0 && (
                          <span className="ml-conf">
                            ({Math.round(prediction.ml_confidence * 100)}% confidence)
                          </span>
                        )}
                        {prediction.ml_agrees != null && (
                          <span className="ml-status">
                            {prediction.ml_agrees ? "\u2713 Consistent with rule engine" : "\u26a1 Differs from rule engine"}
                          </span>
                        )}
                      </div>
                    </details>
                  )}
                </>
              )}

              {/* Result footer */}
              <div className="result-footer">
                Checked {prediction.created_at ? new Date(prediction.created_at).toLocaleString() : "\u2014"}
              </div>
            </div>
          )}

          {/* -- Transaction Details card -- */}
          <div className="form-card detail-card">
            <h3>Transaction Details</h3>

            {/* Submission metadata row */}
            <div className="detail-meta-row">
              <span className="detail-meta-item">
                <span className="detail-meta-label">Check ID</span>
                <span className="detail-meta-val mono">#{id}</span>
              </span>
              <span className="detail-meta-item">
                <span className="detail-meta-label">Submitted</span>
                <span className="detail-meta-val">
                  {check.created_at ? new Date(check.created_at).toLocaleString() : "\u2014"}
                </span>
              </span>
              <span className="detail-meta-item">
                <span className="detail-meta-label">Method</span>
                <span className="detail-meta-val">
                  {inputMethodLabel(check.input_method || check.source_channel)}
                </span>
              </span>
              {check.wallet_id && (
                <span className="detail-meta-item">
                  <span className="detail-meta-label">Wallet</span>
                  <span className="detail-meta-val mono">#{check.wallet_id}</span>
                </span>
              )}
            </div>

            {/* Extracted transaction fields - only shown when at least one field is present */}
            {(() => {
              const sender    = check.sender_name || check.counterparty_name;
              const senderNum = check.sender_number || check.counterparty_number;
              const hasFields = sender || senderNum || check.amount != null
                || check.mtn_transaction_id || check.balance_before != null
                || check.balance_after != null;
              if (!hasFields) return null;

              return (
                <>
                  <h4 className="detail-section-heading">Extracted Fields</h4>
                  <div className="extracted-grid detail-grid">

                    {check.amount != null && (
                      <div className="extracted-item extracted-item--highlight">
                        <span className="extracted-label">Amount Received</span>
                        <span className="extracted-value amount">
                          {check.currency || "GHS"} {Number(check.amount).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {sender && (
                      <div className="extracted-item">
                        <span className="extracted-label">Sender Name</span>
                        <span className="extracted-value">{sender}</span>
                      </div>
                    )}

                    {senderNum && (
                      <div className="extracted-item">
                        <span className="extracted-label">Sender Number</span>
                        <span className="extracted-value mono">{senderNum}</span>
                      </div>
                    )}

                    {check.mtn_transaction_id && (
                      <div className="extracted-item">
                        <span className="extracted-label">MTN Transaction ID</span>
                        <span className="extracted-value mono">{check.mtn_transaction_id}</span>
                      </div>
                    )}

                    {check.balance_before != null && (
                      <div className="extracted-item">
                        <span className="extracted-label">Balance Before</span>
                        <span className="extracted-value">
                          GHS {Number(check.balance_before).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {check.balance_after != null && (
                      <div className="extracted-item">
                        <span className="extracted-label">Balance After</span>
                        <span className="extracted-value">
                          GHS {Number(check.balance_after).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {/* Net change - computed when both balance values are present */}
                    {check.balance_before != null && check.balance_after != null && (
                      <div className="extracted-item">
                        <span className="extracted-label">Net Change</span>
                        <span className="extracted-value">
                          GHS {Number(check.balance_after - check.balance_before).toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                </>
              );
            })()}

            {/* Raw SMS text */}
            {check.raw_text && (
              <div className="detail-raw-section">
                <div className="detail-raw-header">
                  <h4 className="detail-section-heading">Original Message</h4>
                  <button
                    className="detail-raw-copy-btn"
                    onClick={() => navigator.clipboard.writeText(check.raw_text)}
                    title="Copy message text"
                  >
                    Copy
                  </button>
                </div>
                <pre className="raw-text-block">{check.raw_text}</pre>
              </div>
            )}
          </div>

          {/* Action buttons */}
          <div className="btn-row">
            <Link to="/check-message" className="btn btn-primary">
              Check Another Message
            </Link>
            <Link to="/message-history" className="btn btn-outline">
              &larr; Back to History
            </Link>
          </div>
        </>
      )}
    </PageLayout>
  );
}

export default MessageCheckDetail;