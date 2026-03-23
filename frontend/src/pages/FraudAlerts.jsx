import React, { useState, useEffect } from "react";
import api from "../services/api";

const formatDateTime = (value) => {
  if (!value) {
    return "Time not available";
  }

  return new Date(value).toLocaleString("en-GH", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const friendlyAlertTitle = (alert) => {
  const type = (alert?.alertType || "").toLowerCase();

  if (type.includes("deposit")) {
    return "Suspicious deposit detected";
  }

  if (type.includes("blocked") || type.includes("transfer")) {
    return "Blocked transaction detected";
  }

  if (type.includes("wallet")) {
    return "Wallet protection alert";
  }

  return alert?.alertType || "Wallet protection alert";
};

const friendlyAlertMessage = (alert) => {
  return (
    alert?.description ||
    alert?.alertMessage ||
    "The system noticed a transaction pattern that does not look normal."
  );
};

function FraudAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchFraudAlerts = async () => {
      try {
        setLoading(true);
        const response = await api.get('/fraud-alerts');
        setAlerts(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        setError(err.message || 'Failed to fetch fraud alerts');
      } finally {
        setLoading(false);
      }
    };

    fetchFraudAlerts();
  }, []);

  const getRiskLevel = (riskScore) => {
    if (riskScore >= 80) return { level: 'High', color: '#dc2626' };
    if (riskScore >= 50) return { level: 'Medium', color: '#d97706' };
    return { level: 'Low', color: '#16a34a' };
  };

  const highRiskAlerts = alerts.filter((alert) => (alert?.riskScore || 0) >= 80).length;
  const activeAlerts = alerts.filter((alert) => alert?.status !== "resolved").length;
  const resolvedAlerts = alerts.filter((alert) => alert?.status === "resolved").length;

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1>Fraud Alerts</h1>
          <p>Understand why the system raised an alert and what the user should do next.</p>
        </div>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading fraud alerts...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1>Fraud Alerts</h1>
          <p>Understand why the system raised an alert and what the user should do next.</p>
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
        <h1>Fraud Alerts</h1>
        <p>Understand why the system raised an alert and what the user should do next.</p>
      </div>

      <div className="message-box info">
        <span className="message-icon">🛡️</span>
        Alerts do not always mean money is lost. They show when the wallet protection system sees a pattern that needs review or an action.
      </div>

      <div className="customer-insight-grid alert-insight-grid">
        <div className="customer-insight-card danger">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🚨</span>
            <div>
              <h3>High-risk alerts</h3>
              <p>These alerts need urgent attention because the risk score is high.</p>
            </div>
          </div>
          <div className="customer-insight-value">{highRiskAlerts}</div>
          <p className="customer-insight-footnote">High-risk items should be reviewed before the user tries another transaction.</p>
        </div>

        <div className="customer-insight-card warning">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🔔</span>
            <div>
              <h3>Open alerts</h3>
              <p>Alerts that are still active or waiting for a final decision.</p>
            </div>
          </div>
          <div className="customer-insight-value">{activeAlerts}</div>
          <p className="customer-insight-footnote">These items still need action, review, or follow-up.</p>
        </div>

        <div className="customer-insight-card info">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">✅</span>
            <div>
              <h3>Resolved alerts</h3>
              <p>Alerts that were checked and closed by the protection process.</p>
            </div>
          </div>
          <div className="customer-insight-value">{resolvedAlerts}</div>
          <p className="customer-insight-footnote">Resolved items help show that the protection workflow is working.</p>
        </div>
      </div>

      {Array.isArray(alerts) && alerts.length > 0 ? (
        <div className="alerts-list">
          {alerts.map((alert) => {
            const riskInfo = getRiskLevel(alert?.riskScore || 0);
            const isResolved = alert?.status === "resolved";

            return (
              <div className={`alert-detail-card ${isResolved ? "resolved" : riskInfo.level.toLowerCase()}`} key={alert?._id || Math.random()}>
                <div className="alert-detail-header">
                  <div>
                    <div className="alert-detail-badges">
                      <span className={`severity-badge severity-${riskInfo.level}`}>{riskInfo.level} Risk</span>
                      <span className={`badge ${isResolved ? "badge-success" : "badge-warning"}`}>
                        {(alert?.status || "unknown").toUpperCase()}
                      </span>
                    </div>
                    <h2>{friendlyAlertTitle(alert)}</h2>
                    <p>{friendlyAlertMessage(alert)}</p>
                  </div>
                  <div className="alert-detail-score">
                    <span>Risk score</span>
                    <strong style={{ color: riskInfo.color }}>{alert?.riskScore || 0}/100</strong>
                  </div>
                </div>

                <div className="alert-detail-grid">
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">What it means</span>
                    <p>
                      {isResolved
                        ? "This alert has already been reviewed and closed by the protection process."
                        : "This alert means the system noticed wallet activity that does not look normal and should be checked."}
                    </p>
                  </div>
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">Recommended action</span>
                    <p>{alert?.recommendedAction || "Review the transaction and confirm the customer details."}</p>
                  </div>
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">Recorded time</span>
                    <p>{formatDateTime(alert?.createdAt)}</p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-state-icon">✅</div>
          <p>No fraud alerts found. The wallet protection system is currently clear.</p>
        </div>
      )}
    </div>
  );
}

export default FraudAlerts;