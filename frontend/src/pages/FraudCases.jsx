import React, { useEffect, useState } from "react";
import api from "../services/api";

function FraudCases() {
  const [fraudCases, setFraudCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchFraudCases = async () => {
      try {
        setLoading(true);
        const response = await api.get("/fraud-cases");
        setFraudCases(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        setError(err.message || "Failed to fetch fraud cases");
      } finally {
        setLoading(false);
      }
    };

    fetchFraudCases();
  }, []);

  const getRiskScore = (fraudCase) => {
    return typeof fraudCase?.riskScore === "number" ? fraudCase.riskScore : 0;
  };

  const getRiskStyle = (score) => {
    if (score >= 80) return { label: "High", color: "#dc2626" };
    if (score >= 50) return { label: "Medium", color: "#d97706" };
    return { label: "Low", color: "#16a34a" };
  };

  const getStatusClass = (status) => {
    const s = (status || "").toLowerCase();
    if (s === "resolved") return "badge-success";
    if (s === "under_review") return "badge-warning";
    if (s === "confirmed_fraud") return "badge-danger";
    return "badge-info";
  };

  const formatStatus = (status) => {
    if (!status) return "N/A";
    return status.replace(/_/g, " ").toUpperCase();
  };

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1>Fraud Cases</h1>
          <p>Investigate confirmed and pending fraud cases</p>
        </div>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading fraud cases...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1>Fraud Cases</h1>
          <p>Investigate confirmed and pending fraud cases</p>
        </div>
        <div className="message-box error">
          <span className="message-icon">❌</span>
          {error}
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="page-header">
        <h1>Fraud Cases</h1>
        <p>Investigate confirmed and pending fraud cases</p>
      </div>

      {fraudCases.length > 0 ? (
        <div className="table-container">
          <div className="table-header">
            <h2>🧩 Case Records</h2>
            <span className="table-count">{fraudCases.length} case{fraudCases.length !== 1 ? 's' : ''}</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Customer</th>
                  <th>Phone</th>
                  <th>Pattern</th>
                  <th>Explanation</th>
                  <th>Risk</th>
                  <th>Status</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {fraudCases.map((fraudCase) => {
                  const riskScore = getRiskScore(fraudCase);
                  const riskStyle = getRiskStyle(riskScore);

                  const customerName =
                    fraudCase?.customerName ||
                    fraudCase?.triggerTransaction?.fullName ||
                    "N/A";

                  const phoneNumber =
                    fraudCase?.phoneNumber ||
                    fraudCase?.triggerTransaction?.phoneNumber ||
                    "N/A";

                  const fraudPattern =
                    fraudCase?.fraudPattern ||
                    fraudCase?.triggerTransaction?.fraudReason ||
                    "Suspicious linked transaction pattern";

                  const explanation =
                    fraudCase?.explanation ||
                    "Case requires analyst review";

                  const status =
                    fraudCase?.status ||
                    "new";

                  const recommendedAction =
                    fraudCase?.recommendedAction ||
                    "Review linked transactions and contact customer for verification";

                  return (
                    <tr key={fraudCase?._id || `${customerName}-${phoneNumber}`}>
                      <td style={{ fontWeight: 600 }}>{customerName}</td>
                      <td>{phoneNumber}</td>
                      <td>{fraudPattern}</td>
                      <td>{explanation}</td>
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                          <span className={`severity-badge severity-${riskStyle.label}`}>
                            {riskStyle.label}
                          </span>
                          <span style={{ fontWeight: 600, color: riskStyle.color, fontSize: "0.85rem" }}>
                            {riskScore}/100
                          </span>
                        </div>
                      </td>
                      <td>
                        <span className={`badge ${getStatusClass(status)}`}>
                          {formatStatus(status)}
                        </span>
                      </td>
                      <td>{recommendedAction}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-state-icon">📂</div>
          <p>No fraud cases found.</p>
        </div>
      )}
    </div>
  );
}

export default FraudCases;
