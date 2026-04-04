import React, { useState, useEffect } from "react";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";

// ============================================================
// Predictions.jsx — View all fraud predictions
// ============================================================
// Route used: GET /api/predictions
// ============================================================

function Predictions() {
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
      console.error("[Predictions] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  // Row CSS class based on risk
  function rowClass(pred) {
    if (pred.prediction === "suspicious" || pred.risk_level === "high") {
      return "row-danger";
    }
    if (pred.risk_level === "medium") {
      return "row-warning";
    }
    return "";
  }

  // Pill color based on risk level
  function riskPill(level) {
    if (level === "high") return "blocked";
    if (level === "medium") return "review";
    return "trusted";
  }

  return (
    <PageLayout
      title="Fraud Predictions"
      subtitle="Transactions are scored automatically. Review results below."
    >

      {/* Error state */}
      {error && (
        <div className="message-box error">
          <span className="message-icon">❌</span>
          {error}
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading fraud predictions...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && predictions.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">🛡️</div>
          <p>No predictions yet. Add a transaction to see its fraud score.</p>
        </div>
      )}

      {/* Predictions table */}
      {predictions.length > 0 && (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Pred ID</th>
                <th>Txn ID</th>
                <th>Prediction</th>
                <th>Risk Level</th>
                <th>Anomaly Score</th>
                <th>Explanation</th>
                <th>Amount Z-Score</th>
                <th>Balance Drain</th>
                <th>New Device</th>
                <th>New Location</th>
                <th>Velocity 1d</th>
              </tr>
            </thead>
            <tbody>
              {predictions.map((p) => (
                <tr key={p.id} className={rowClass(p)}>
                  <td>{p.id}</td>
                  <td>{p.transaction_id}</td>
                  <td>
                    <span className={`status-pill ${p.prediction === "suspicious" ? "blocked" : "trusted"}`}>
                      {p.prediction}
                    </span>
                  </td>
                  <td>
                    <span className={`status-pill ${riskPill(p.risk_level)}`}>
                      {p.risk_level}
                    </span>
                  </td>
                  <td>{p.anomaly_score}</td>
                  <td className="explanation-cell">{p.explanation}</td>
                  <td>{p.amount_zscore}</td>
                  <td>{p.balance_drain_ratio}</td>
                  <td>{p.is_new_device ? "Yes" : "No"}</td>
                  <td>{p.is_new_location ? "Yes" : "No"}</td>
                  <td>{p.velocity_1day}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}

export default Predictions;
