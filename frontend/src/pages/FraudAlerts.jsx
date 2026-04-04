import React, { useState, useEffect } from "react";
import { authFetch } from "../services/api";

// ============================================================
// FraudAlerts.jsx — View fraud predictions (Phase 3)
// ============================================================
// Route used: GET /api/predictions
// Each prediction includes joined transaction details:
//   wallet_id, amount, transaction_type, direction, transaction_time
// ============================================================

function FraudAlerts() {
  const [predictions, setPredictions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchPredictions();
  }, []);

  async function fetchPredictions() {
    const token = localStorage.getItem("token");
    if (!token) {
      setError("You must log in first.");
      setLoading(false);
      return;
    }

    try {
      const { data, response } = await authFetch("/api/predictions");
      if (response.ok) {
        setPredictions(data.predictions || []);
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load predictions.");
      }
    } catch (err) {
      console.error("[FraudAlerts] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  function riskColor(level) {
    if (level === "high") return { background: "#fef2f2", color: "#dc2626", border: "#fecaca" };
    if (level === "medium") return { background: "#fffbeb", color: "#d97706", border: "#fde68a" };
    return { background: "#f0fdf4", color: "#16a34a", border: "#bbf7d0" };
  }

  return (
    <div>
      <div className="page-header">
        <h1>Fraud Alerts</h1>
        <p>Transactions are scored automatically. Flagged items appear here.</p>
      </div>

      {error && (
        <div className="message-box error">
          <span className="message-icon">❌</span>
          {error}
        </div>
      )}

      {loading && <p>Loading predictions...</p>}

      {!loading && !error && predictions.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">✅</div>
          <p>No fraud alerts yet. Transactions will be scored as they come in.</p>
        </div>
      )}

      {predictions.length > 0 && (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Txn ID</th>
                <th>Type</th>
                <th>Direction</th>
                <th>Amount</th>
                <th>Time</th>
                <th>Prediction</th>
                <th>Risk</th>
                <th>Score</th>
                <th>Explanation</th>
              </tr>
            </thead>
            <tbody>
              {predictions.map((p) => {
                const rc = riskColor(p.risk_level);
                return (
                  <tr key={p.id}>
                    <td>{p.transaction_id}</td>
                    <td>{p.transaction_type}</td>
                    <td>{p.direction}</td>
                    <td style={{ fontWeight: 600 }}>GHS {Number(p.amount).toFixed(2)}</td>
                    <td>{p.transaction_time || "—"}</td>
                    <td>
                      <span
                        className="status-pill"
                        style={{
                          background: rc.background,
                          color: rc.color,
                          borderColor: rc.border,
                          borderWidth: 1,
                          borderStyle: "solid",
                        }}
                      >
                        {p.prediction}
                      </span>
                    </td>
                    <td>
                      <span
                        className="status-pill"
                        style={{
                          background: rc.background,
                          color: rc.color,
                          borderColor: rc.border,
                          borderWidth: 1,
                          borderStyle: "solid",
                        }}
                      >
                        {p.risk_level}
                      </span>
                    </td>
                    <td>{p.anomaly_score}</td>
                    <td style={{ fontSize: 13, maxWidth: 300 }}>{p.explanation}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default FraudAlerts;
