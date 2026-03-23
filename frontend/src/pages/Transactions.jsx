import React, { useEffect, useState } from "react";
import api from "../services/api";

const TYPE_LABELS = {
  deposit: "Deposit",
  cashin: "Cash In",
  transfer_in: "Transfer In",
  transfer_out: "Transfer Out",
  cashout: "Cash Out",
  withdrawal: "Withdrawal",
  transfer: "Transfer",
};

const trustBadgeClass = (level) => {
  if (level === "trusted") return "badge-trust-trusted";
  if (level === "high_risk") return "badge-trust-high-risk";
  return "badge-trust-warning";
};

const verificationBadgeClass = (status) => {
  if (status === "verified") return "badge-verify-verified";
  if (status === "suspicious") return "badge-verify-suspicious";
  return "badge-verify-unverified";
};

const directionBadgeClass = (dir) => {
  return dir === "outgoing" ? "badge-dir-outgoing" : "badge-dir-incoming";
};

const formatAmount = (amount) =>
  Number(amount || 0).toLocaleString("en-GH", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

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

const formatTrustLabel = (trustLevel) => {
  if (trustLevel === "trusted") return "Trusted";
  if (trustLevel === "high_risk") return "High Risk";
  return "Warning";
};

const formatVerificationLabel = (verificationStatus) => {
  if (verificationStatus === "verified") return "Verified";
  if (verificationStatus === "suspicious") return "Suspicious";
  return "Under Review";
};

const friendlyTypeTitle = (tx) => {
  const type = TYPE_LABELS[tx?.transactionType] || tx?.transactionType || "Transaction";
  const dir = tx?.transactionDirection === "outgoing" ? "outgoing" : "incoming";
  return `${type} (${dir})`;
};

const getProtectionSummary = (tx) => {
  const isBlocked = tx?.blocked || tx?.isBlocked || tx?.status === "blocked";
  const isSuspicious = tx?.isSuspicious || tx?.verificationStatus === "suspicious";
  const isIncoming = tx?.transactionDirection === "incoming";
  const isOutgoing = tx?.transactionDirection === "outgoing";

  if (isBlocked) {
    return {
      tone: "danger",
      label: "Blocked for Safety",
      message: tx?.blockReason || "This transaction was stopped before money could move.",
      explanation:
        tx?.fraudExplanation ||
        "The system saw a pattern that looks risky and protected the wallet immediately.",
      action: tx?.recommendedAction || "Confirm the receiver before sending again.",
    };
  }

  if (isSuspicious && isIncoming) {
    return {
      tone: "warning",
      label: "Suspicious",
      message: tx?.fraudExplanation || "This incoming money is being checked before it can be trusted.",
      explanation:
        tx?.fraudExplanation ||
        "The source or pattern of the deposit does not look normal for this wallet.",
      action: tx?.recommendedAction || "Wait for verification before spending or sending the funds.",
    };
  }

  if (tx?.verificationStatus === "unverified" || tx?.status === "pending") {
    return {
      tone: "info",
      label: "Under Review",
      message: "The system is still checking this transaction.",
      explanation:
        tx?.fraudExplanation ||
        "The transaction is pending final checks before it is treated as fully safe.",
      action: tx?.recommendedAction || "Wait for the status to change before making a next move.",
    };
  }

  return {
    tone: "success",
    label: "Trusted",
    message: "No protection issue has been found on this transaction.",
    explanation: "The transaction matches normal wallet behaviour.",
    action: "No action is needed.",
  };
};

function Transactions() {
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedId, setExpandedId] = useState(null);

  useEffect(() => {
    const fetchTransactions = async () => {
      try {
        setLoading(true);
        const response = await api.get("/transactions");
        setTransactions(Array.isArray(response.data) ? response.data : []);
      } catch (err) {
        setError(err.message || "Failed to fetch transactions");
      } finally {
        setLoading(false);
      }
    };

    fetchTransactions();
  }, []);

  const toggleExpand = (id) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const suspiciousDeposits = transactions.filter((tx) => {
    const isIncomingDeposit = ["deposit", "cashin", "transfer_in"].includes(tx?.transactionType);
    const isSuspicious = tx?.isSuspicious || tx?.verificationStatus === "suspicious";
    return isIncomingDeposit && isSuspicious;
  }).length;

  const blockedTransactions = transactions.filter(
    (tx) => tx?.blocked || tx?.isBlocked || tx?.status === "blocked"
  ).length;

  const fundsOnHold = transactions.filter((tx) => tx?.availableForUse === false).length;

  const needsAttention = blockedTransactions > 0 || suspiciousDeposits > 0;

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1>Transactions</h1>
          <p>See every wallet movement and understand which ones need your attention.</p>
        </div>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading transactions...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1>Transactions</h1>
          <p>See every wallet movement and understand which ones need your attention.</p>
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
        <h1>Transactions</h1>
        <p>See every wallet movement and understand which ones need your attention.</p>
      </div>

      {/* ── Protection status panel (matches Dashboard) ── */}
      <div className={`protection-status-panel ${needsAttention ? "warning" : "safe"}`}>
        <div className="protection-status-icon">{needsAttention ? "⚠️" : "✅"}</div>
        <div className="protection-status-content">
          <h3>
            {needsAttention
              ? "Some transactions need your attention before you use the money."
              : "All transactions look normal. No risky wallet activity found."}
          </h3>
          <ul className="protection-status-list">
            <li>
              <span className="status-pill trusted">Trusted</span>
              {fundsOnHold > 0
                ? `${fundsOnHold} transaction${fundsOnHold !== 1 ? "s are" : " is"} on hold until checks finish`
                : "No money is currently on hold"}
            </li>
            <li>
              <span className="status-pill review">Review</span>
              {suspiciousDeposits > 0
                ? `${suspiciousDeposits} suspicious deposit${suspiciousDeposits !== 1 ? "s need" : " needs"} verification`
                : "No suspicious deposit detected"}
            </li>
            <li>
              <span className="status-pill blocked">Blocked</span>
              {blockedTransactions > 0
                ? `${blockedTransactions} transaction${blockedTransactions !== 1 ? "s were" : " was"} stopped to protect the wallet`
                : "No transaction has been blocked"}
            </li>
          </ul>
        </div>
      </div>

      {/* ── Insight cards (matches Dashboard & Fraud Alerts) ── */}
      <div className="customer-insight-grid transaction-insight-grid">
        <div className="customer-insight-card warning">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🔎</span>
            <div>
              <h3>Suspicious deposits</h3>
              <p>Incoming money that needs extra checks before it can be trusted.</p>
            </div>
          </div>
          <div className="customer-insight-value">{suspiciousDeposits}</div>
          <p className="customer-insight-footnote">Review these deposits before cash out or transfer out.</p>
        </div>

        <div className="customer-insight-card danger">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">⛔</span>
            <div>
              <h3>Blocked transactions</h3>
              <p>Payments stopped because the risk looked too high.</p>
            </div>
          </div>
          <div className="customer-insight-value">{blockedTransactions}</div>
          <p className="customer-insight-footnote">Your wallet stays protected because the money did not move.</p>
        </div>

        <div className="customer-insight-card info">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🛡️</span>
            <div>
              <h3>Funds on hold</h3>
              <p>Money that cannot be used until verification is completed.</p>
            </div>
          </div>
          <div className="customer-insight-value">{fundsOnHold}</div>
          <p className="customer-insight-footnote">This helps prevent fraud from spreading through your wallet.</p>
        </div>
      </div>

      {/* ── Transaction list (card style matching Fraud Alerts) ── */}
      {transactions.length > 0 ? (
        <div className="alerts-list">
          {transactions.map((tx) => {
            const id = tx?._id || Math.random().toString();
            const isExpanded = expandedId === id;
            const isBlocked = tx?.blocked || tx?.isBlocked || tx?.status === "blocked";
            const protection = getProtectionSummary(tx);

            return (
              <div className={`alert-detail-card ${protection.tone === "success" ? "low" : protection.tone === "warning" ? "medium" : protection.tone === "danger" ? "high" : "low"}`} key={id}>
                {/* ── Card header with badges + amount (mirrors alert-detail-header) ── */}
                <div className="alert-detail-header">
                  <div>
                    <div className="alert-detail-badges">
                      <span className={`protection-chip ${protection.tone}`}>{protection.label}</span>
                      <span className={`badge ${directionBadgeClass(tx?.transactionDirection)}`}>
                        {tx?.transactionDirection === "outgoing" ? "OUTGOING" : "INCOMING"}
                      </span>
                      <span className={`badge ${verificationBadgeClass(tx?.verificationStatus)}`}>
                        {formatVerificationLabel(tx?.verificationStatus).toUpperCase()}
                      </span>
                      <span className={`badge ${trustBadgeClass(tx?.trustLevel)}`}>
                        {formatTrustLabel(tx?.trustLevel).toUpperCase()}
                      </span>
                      {isBlocked && <span className="badge badge-danger">BLOCKED</span>}
                    </div>
                    <h2>{friendlyTypeTitle(tx)}</h2>
                    <p>{protection.message}</p>
                  </div>
                  <div className="alert-detail-score">
                    <span>Amount (GHS)</span>
                    <strong style={{ color: isBlocked ? "#dc2626" : "#0f172a" }}>
                      {formatAmount(tx?.amount)}
                    </strong>
                  </div>
                </div>

                {/* ── Quick-glance grid (mirrors alert-detail-grid) ── */}
                <div className="alert-detail-grid">
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">Customer</span>
                    <p>{tx?.fullName || "N/A"} &middot; {tx?.phoneNumber || "N/A"}</p>
                  </div>
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">Transaction type</span>
                    <p>{TYPE_LABELS[tx?.transactionType] || tx?.transactionType || "N/A"}</p>
                  </div>
                  <div className="alert-detail-item">
                    <span className="tx-detail-label">Recorded time</span>
                    <p>{formatDateTime(tx?.timestamp)}</p>
                  </div>
                </div>

                {/* ── Expand/collapse button ── */}
                <div style={{ marginTop: "0.85rem" }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => toggleExpand(id)}
                  >
                    {isExpanded ? "Hide protection details" : "View protection details"}
                  </button>
                </div>

                {/* ── Expanded detail panel ── */}
                {isExpanded && (
                  <div className="tx-card-details">
                    {isBlocked && (
                      <div className="message-box error">
                        <span className="message-icon">⛔</span>
                        <div>
                          <strong>This transaction was blocked for your safety.</strong>
                          <p style={{ margin: "0.25rem 0 0" }}>
                            {tx?.blockReason || "Transaction blocked for security reasons."}
                          </p>
                        </div>
                      </div>
                    )}

                    <div className="tx-detail-callout-grid">
                      <div className="tx-detail-callout">
                        <span className="tx-detail-label">What happened</span>
                        <p className="tx-detail-text">{protection.message}</p>
                      </div>
                      <div className="tx-detail-callout">
                        <span className="tx-detail-label">Why it was flagged</span>
                        <p className="tx-detail-text">{protection.explanation}</p>
                      </div>
                      <div className="tx-detail-callout info">
                        <span className="tx-detail-label">What to do next</span>
                        <p className="tx-detail-text tx-detail-text-info">{protection.action}</p>
                      </div>
                    </div>

                    <div className="tx-detail-grid">
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Transaction Type</span>
                        <span className="tx-detail-value">
                          {TYPE_LABELS[tx?.transactionType] || tx?.transactionType || "N/A"}
                        </span>
                      </div>
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Direction</span>
                        <span className="tx-detail-value">
                          <span className={`badge ${directionBadgeClass(tx?.transactionDirection)}`}>
                            {tx?.transactionDirection === "outgoing" ? "OUTGOING" : "INCOMING"}
                          </span>
                        </span>
                      </div>
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Verification</span>
                        <span className="tx-detail-value">
                          <span className={`badge ${verificationBadgeClass(tx?.verificationStatus)}`}>
                            {formatVerificationLabel(tx?.verificationStatus).toUpperCase()}
                          </span>
                        </span>
                      </div>
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Trust Level</span>
                        <span className="tx-detail-value">
                          <span className={`badge ${trustBadgeClass(tx?.trustLevel)}`}>
                            {formatTrustLabel(tx?.trustLevel).toUpperCase()}
                          </span>
                        </span>
                      </div>
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Blocked</span>
                        <span className="tx-detail-value">
                          {isBlocked ? (
                            <span className="badge badge-danger">YES</span>
                          ) : (
                            <span className="badge badge-success">NO</span>
                          )}
                        </span>
                      </div>
                      <div className="tx-detail-item">
                        <span className="tx-detail-label">Status</span>
                        <span className="tx-detail-value">
                          <span
                            className={`badge ${
                              tx?.status === "blocked"
                                ? "badge-danger"
                                : tx?.status === "completed"
                                ? "badge-success"
                                : tx?.status === "failed"
                                ? "badge-danger"
                                : "badge-warning"
                            }`}
                          >
                            {(tx?.status || "N/A").toUpperCase()}
                          </span>
                        </span>
                      </div>
                    </div>

                    <div className="tx-detail-section">
                      <span className="tx-detail-label">Block Reason</span>
                      <p className="tx-detail-text tx-detail-text-danger">
                        {tx?.blockReason || "No block reason. This transaction is not blocked."}
                      </p>
                    </div>

                    <div className="tx-detail-section">
                      <span className="tx-detail-label">Fraud Explanation</span>
                      <p className="tx-detail-text">
                        {tx?.fraudExplanation || "No suspicious pattern detected."}
                      </p>
                    </div>

                    <div className="tx-detail-section">
                      <span className="tx-detail-label">Recommended Action</span>
                      <p className="tx-detail-text tx-detail-text-info">
                        {tx?.recommendedAction || "No action required — transaction verified."}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          <div className="empty-state-icon">📋</div>
          <p>No transactions found. The wallet has no recorded activity yet.</p>
        </div>
      )}
    </div>
  );
}

export default Transactions;
