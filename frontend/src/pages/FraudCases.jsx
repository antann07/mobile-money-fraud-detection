import React from "react";

// FraudCases.jsx — No backend endpoint exists for fraud cases.
// Kept as an informational placeholder.

function FraudCases() {
  return (
    <div>
      <div className="page-header">
        <h1>Fraud Cases</h1>
        <p>Review confirmed and pending fraud cases.</p>
      </div>

      <div className="message-box info">
        <span className="message-icon">🚧</span>
        Fraud case management is planned for a future phase.
        Check the <strong>Fraud Alerts</strong> page for current prediction results.
      </div>

      <div className="empty-state">
        <div className="empty-state-icon">📂</div>
        <p>No fraud cases yet.</p>
      </div>
    </div>
  );
}

export default FraudCases;
