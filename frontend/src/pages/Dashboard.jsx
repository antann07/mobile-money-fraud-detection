import React, { useEffect, useState } from 'react';
import api from '../services/api';

const TYPE_LABELS = {
  deposit: 'Deposit',
  cashin: 'Cash In',
  transfer_in: 'Transfer In',
  transfer_out: 'Transfer Out',
  cashout: 'Cash Out',
  withdrawal: 'Withdrawal',
  transfer: 'Transfer',
};

const formatAmount = (amount) =>
  Number(amount || 0).toLocaleString('en-GH', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

const formatDateTime = (value) => {
  if (!value) {
    return 'Time not available';
  }

  return new Date(value).toLocaleString('en-GH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

const getProtectionEvent = (transaction) => {
  const isBlocked = transaction?.blocked || transaction?.isBlocked || transaction?.status === 'blocked';
  const isSuspicious = transaction?.isSuspicious || transaction?.verificationStatus === 'suspicious';
  const isIncoming = transaction?.transactionDirection === 'incoming';
  const isOutgoing = transaction?.transactionDirection === 'outgoing';
  const typeLabel = TYPE_LABELS[transaction?.transactionType] || transaction?.transactionType || 'Transaction';

  if (isBlocked && isOutgoing) {
    return {
      tone: 'danger',
      label: 'Blocked transfer',
      message: transaction?.blockReason || 'A risky outgoing payment was stopped before money left the wallet.',
      action: transaction?.recommendedAction || 'Confirm the receiver before trying again.',
      typeLabel,
    };
  }

  if (isSuspicious && isIncoming) {
    return {
      tone: 'warning',
      label: 'Suspicious deposit',
      message: transaction?.fraudExplanation || 'This incoming money does not match the normal pattern on the wallet.',
      action: transaction?.recommendedAction || 'Wait for verification before spending the money.',
      typeLabel,
    };
  }

  return {
    tone: 'info',
    label: 'Under review',
    message: transaction?.fraudExplanation || 'The transaction is still being checked by the protection system.',
    action: transaction?.recommendedAction || 'Check the transaction details and wait for confirmation.',
    typeLabel,
  };
};

function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [protectionIndicators, setProtectionIndicators] = useState({
    walletTransactions: 0,
    fraudWarnings: 0,
    blockedTransactions: 0,
    suspiciousDeposits: 0,
    underReview: 0,
    blockedOutgoing: 0,
    fundsOnHold: 0,
  });
  const [recentProtectionEvents, setRecentProtectionEvents] = useState([]);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const [summaryResponse, transactionsResponse] = await Promise.all([
          api.get('/dashboard/summary'),
          api.get('/transactions'),
        ]);

        const summaryData = summaryResponse.data || {};
        const transactions = Array.isArray(transactionsResponse.data)
          ? transactionsResponse.data
          : [];

        const blockedTransactions = transactions.filter(
          (tx) => tx?.blocked || tx?.isBlocked || tx?.status === 'blocked'
        );

        const suspiciousDeposits = transactions.filter((tx) => {
          const isDeposit = ['deposit', 'cashin', 'transfer_in'].includes(tx?.transactionType);
          const isSuspicious = tx?.isSuspicious || tx?.verificationStatus === 'suspicious';
          return isDeposit && isSuspicious;
        });

        const underReview = transactions.filter(
          (tx) => tx?.verificationStatus === 'unverified' || tx?.status === 'pending'
        );

        const blockedOutgoing = blockedTransactions.filter(
          (tx) => tx?.transactionDirection === 'outgoing'
        );

        const fundsOnHold = transactions.filter((tx) => tx?.availableForUse === false).length;

        const recentEvents = transactions
          .filter(
            (tx) =>
              tx?.blocked ||
              tx?.isBlocked ||
              tx?.status === 'blocked' ||
              tx?.isSuspicious ||
              tx?.verificationStatus === 'suspicious' ||
              tx?.status === 'pending'
          )
          .sort((left, right) => new Date(right?.timestamp || 0) - new Date(left?.timestamp || 0))
          .slice(0, 4);

        setProtectionIndicators({
          walletTransactions: summaryData?.totalTransactions || transactions.length,
          fraudWarnings: summaryData?.totalFraudAlerts || 0,
          blockedTransactions: blockedTransactions.length,
          suspiciousDeposits: suspiciousDeposits.length,
          underReview: underReview.length,
          blockedOutgoing: blockedOutgoing.length,
          fundsOnHold,
        });
        setRecentProtectionEvents(recentEvents);
      } catch (err) {
        setError('Failed to load dashboard data');
        console.error('Dashboard error:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSummary();
  }, []);

  const needsAttention = protectionIndicators.blockedOutgoing > 0 || protectionIndicators.suspiciousDeposits > 0;

  if (loading) {
    return (
      <div>
        <div className="page-header">
          <h1>Wallet Protection Dashboard</h1>
          <p>See suspicious deposits, blocked payments, and how the wallet is being protected.</p>
        </div>
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading dashboard data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <div className="page-header">
          <h1>Wallet Protection Dashboard</h1>
          <p>See suspicious deposits, blocked payments, and how the wallet is being protected.</p>
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
        <h1>Wallet Protection Dashboard</h1>
        <p>See suspicious deposits, blocked payments, and how the wallet is being protected.</p>
      </div>

      <div className={`protection-status-panel ${needsAttention ? 'warning' : 'safe'}`}>
        <div className="protection-status-icon">{needsAttention ? '⚠️' : '🛡️'}</div>
        <div className="protection-status-content">
          <h3>
            {needsAttention
              ? 'Protection is active. Some transactions need attention.'
              : 'Protection is active. No risky wallet movement has been found.'}
          </h3>
          <ul className="protection-status-list">
            <li>
              <span className="status-pill trusted">Safe wallet</span>
              {protectionIndicators.fundsOnHold > 0
                ? `${protectionIndicators.fundsOnHold} transaction${protectionIndicators.fundsOnHold !== 1 ? 's are' : ' is'} on hold until checks are completed`
                : 'No money is currently on hold'}
            </li>
            <li>
              <span className="status-pill review">Review</span>
              {protectionIndicators.suspiciousDeposits > 0
                ? `${protectionIndicators.suspiciousDeposits} suspicious deposit${protectionIndicators.suspiciousDeposits !== 1 ? 's need' : ' needs'} verification`
                : 'No suspicious deposit detected'}
            </li>
            <li>
              <span className="status-pill blocked">Blocked</span>
              {protectionIndicators.blockedOutgoing > 0
                ? `${protectionIndicators.blockedOutgoing} outgoing transaction${protectionIndicators.blockedOutgoing !== 1 ? 's were' : ' was'} stopped to protect the wallet`
                : 'No outgoing transaction has been blocked'}
            </li>
          </ul>
        </div>
      </div>

      <div className="summary-grid">
        <div className="summary-card">
          <div className="card-header">
            <div>
              <h3>Wallet Transactions</h3>
              <div className="summary-value">{protectionIndicators.walletTransactions}</div>
              <p className="summary-note">All wallet activity currently recorded in the system</p>
            </div>
            <div className="card-icon-bg blue">💳</div>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-header">
            <div>
              <h3>Fraud Warnings</h3>
              <div className="summary-value">{protectionIndicators.fraudWarnings}</div>
              <p className="summary-note">Warnings raised when wallet activity looks unusual</p>
            </div>
            <div className="card-icon-bg amber">🔔</div>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-header">
            <div>
              <h3>Blocked Transactions</h3>
              <div className="summary-value">{protectionIndicators.blockedTransactions}</div>
              <p className="summary-note">Risky outgoing transactions stopped before money left the wallet</p>
            </div>
            <div className="card-icon-bg red">🚨</div>
          </div>
        </div>

        <div className="summary-card">
          <div className="card-header">
            <div>
              <h3>Suspicious Deposits</h3>
              <div className="summary-value">{protectionIndicators.suspiciousDeposits}</div>
              <p className="summary-note">Incoming money marked for extra checks before it can be trusted</p>
            </div>
            <div className="card-icon-bg green">✅</div>
          </div>
        </div>
      </div>

      <div className="customer-insight-grid dashboard-insight-grid">
        <div className="customer-insight-card danger">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">⛔</span>
            <div>
              <h3>Blocked transfers</h3>
              <p>The system stops risky outgoing payments before they leave the wallet.</p>
            </div>
          </div>
          <div className="customer-insight-value">{protectionIndicators.blockedOutgoing}</div>
          <p className="customer-insight-footnote">Recommended action: confirm the receiver and transfer reason before trying again.</p>
        </div>

        <div className="customer-insight-card warning">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🔎</span>
            <div>
              <h3>Suspicious deposits</h3>
              <p>Incoming funds that look unusual are marked and watched closely.</p>
            </div>
          </div>
          <div className="customer-insight-value">{protectionIndicators.suspiciousDeposits}</div>
          <p className="customer-insight-footnote">Recommended action: wait for verification before cashing out or sending the money.</p>
        </div>

        <div className="customer-insight-card info">
          <div className="customer-insight-header">
            <span className="customer-insight-icon">🛡️</span>
            <div>
              <h3>Wallet protection</h3>
              <p>Money can be held or reviewed when the pattern does not look normal.</p>
            </div>
          </div>
          <div className="customer-insight-value">{protectionIndicators.fundsOnHold}</div>
          <p className="customer-insight-footnote">Transactions on hold cannot be used until the checks are completed.</p>
        </div>
      </div>

      <div className="dashboard-section-grid">
        <div className="table-container dashboard-section-card">
          <div className="table-header">
            <h2>What Needs Attention</h2>
            <span className="table-count">{protectionIndicators.underReview} under review</span>
          </div>
          <div className="dashboard-action-list">
            <div className="dashboard-action-item">
              <span className="dashboard-action-badge danger">Blocked</span>
              <div>
                <h3>Outgoing payments are stopped when the risk is high</h3>
                <p>This prevents money from moving out before the owner confirms the transaction.</p>
              </div>
            </div>
            <div className="dashboard-action-item">
              <span className="dashboard-action-badge warning">Deposit</span>
              <div>
                <h3>Suspicious deposits stay visible but are treated carefully</h3>
                <p>The system can keep such money on hold until the sender and activity look safe.</p>
              </div>
            </div>
            <div className="dashboard-action-item">
              <span className="dashboard-action-badge info">Action</span>
              <div>
                <h3>Recommended next step for users</h3>
                <p>Check the sender, check the receiver, and wait for the final verification update before using the money.</p>
              </div>
            </div>
          </div>
        </div>

        <div className="table-container dashboard-section-card">
          <div className="table-header">
            <h2>Recent Protection Activity</h2>
            <span className="table-count">{recentProtectionEvents.length} item{recentProtectionEvents.length !== 1 ? 's' : ''}</span>
          </div>
          {recentProtectionEvents.length > 0 ? (
            <div className="protection-activity-list">
              {recentProtectionEvents.map((transaction) => {
                const event = getProtectionEvent(transaction);

                return (
                  <div className={`protection-activity-item ${event.tone}`} key={transaction?._id}>
                    <div className="protection-activity-topline">
                      <span className={`dashboard-action-badge ${event.tone}`}>{event.label}</span>
                      <span className="protection-activity-time">{formatDateTime(transaction?.timestamp)}</span>
                    </div>
                    <h3>{event.typeLabel} of GHS {formatAmount(transaction?.amount)}</h3>
                    <p>{event.message}</p>
                    <div className="protection-activity-meta">
                      <span>{transaction?.fullName || 'Customer not available'}</span>
                      <span>{transaction?.location || 'Location not available'}</span>
                    </div>
                    <div className="protection-activity-action">Recommended action: {event.action}</div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="empty-state dashboard-empty-state">
              <div className="empty-state-icon">✅</div>
              <p>No recent suspicious or blocked transaction has been recorded.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default Dashboard;