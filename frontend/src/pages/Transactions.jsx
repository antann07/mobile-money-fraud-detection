import React, { useState, useEffect } from "react";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";

// ============================================================
// Transactions.jsx — List & add transactions
// ============================================================
// Routes used:
//   GET  /api/transactions      — list user transactions
//   POST /api/transactions/add  — record a new transaction
// ============================================================

function Transactions() {
  // --- List state ---
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // --- Add-form state ---
  const [walletId, setWalletId] = useState("");
  const [transactionRef, setTransactionRef] = useState("");
  const [transactionType, setTransactionType] = useState("deposit");
  const [direction, setDirection] = useState("incoming");
  const [amount, setAmount] = useState("");
  const [balanceBefore, setBalanceBefore] = useState("");
  const [balanceAfter, setBalanceAfter] = useState("");
  const [transactionTime, setTransactionTime] = useState("");
  const [locationInfo, setLocationInfo] = useState("");
  const [deviceInfo, setDeviceInfo] = useState("");
  const [addLoading, setAddLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");

  // --- Fetch on mount ---
  useEffect(() => {
    fetchTransactions();
  }, []);

  async function fetchTransactions() {
    const token = localStorage.getItem("token");
    if (!token) {
      setError("You must log in first.");
      setLoading(false);
      return;
    }

    try {
      const { data, response } = await authFetch("/transactions");
      if (response.ok) {
        setTransactions(data.transactions || []);
      } else if (response.status === 401) {
        setError("Session expired. Please log in again.");
      } else {
        setError(data.errors?.join(" ") || "Failed to load transactions.");
      }
    } catch (err) {
      console.error("[Transactions] Fetch failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  // --- Add transaction ---
  async function handleAdd(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    const token = localStorage.getItem("token");
    if (!token) {
      setMessage("You must log in first.");
      setMessageType("error");
      return;
    }

    setAddLoading(true);

    // --- Client-side validation ---
    if (!walletId || Number(walletId) < 1) {
      setMessage("Please enter a valid Wallet ID (1 or higher).");
      setMessageType("error");
      setAddLoading(false);
      return;
    }
    if (!amount || Number(amount) <= 0) {
      setMessage("Amount must be greater than 0.");
      setMessageType("error");
      setAddLoading(false);
      return;
    }
    if (!transactionTime) {
      setMessage("Transaction time is required.");
      setMessageType("error");
      setAddLoading(false);
      return;
    }

    const payload = {
      wallet_id: Number(walletId),
      transaction_reference: transactionRef || null,
      transaction_type: transactionType,
      direction,
      amount: Number(amount),
      balance_before: balanceBefore ? Number(balanceBefore) : null,
      balance_after: balanceAfter ? Number(balanceAfter) : null,
      transaction_time: transactionTime,
      location_info: locationInfo || null,
      device_info: deviceInfo || null,
      source_channel: "app",
    };

    try {
      const { data, response } = await authFetch("/transactions/add", "POST", payload);

      if (response.status === 201) {
        setMessage("Transaction added and scored successfully!");
        setMessageType("success");
        setTransactionRef("");
        setAmount("");
        setBalanceBefore("");
        setBalanceAfter("");
        setTransactionTime("");
        setLocationInfo("");
        setDeviceInfo("");
        fetchTransactions();
      } else if (response.status === 401) {
        setMessage("Session expired. Please log in again.");
        setMessageType("error");
      } else if (response.status === 403) {
        setMessage("Wallet does not belong to you.");
        setMessageType("error");
      } else {
        const errors = data.errors || ["Failed to add transaction."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : errors);
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Transactions] Add failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setAddLoading(false);
    }
  }

  return (
    <PageLayout
      title="Transactions"
      subtitle="All wallet movements — deposits, withdrawals, and transfers."
    >

      {/* Feedback message */}
      {message && (
        <div className={`message-box ${messageType}`}>
          <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
          {message}
        </div>
      )}

      {/* -------- Add Transaction Form -------- */}
      <div className="form-card">
        <h3>Add a Transaction</h3>
        <form onSubmit={handleAdd}>
          {/* Row 1: wallet_id, reference */}
          <div className="form-row">
            <div className="form-group">
              <label>Wallet ID</label>
              <input type="number" min="1" value={walletId} onChange={(e) => setWalletId(e.target.value)} required placeholder="e.g. 1" />
            </div>
            <div className="form-group">
              <label>Reference (optional)</label>
              <input type="text" value={transactionRef} onChange={(e) => setTransactionRef(e.target.value)} placeholder="e.g. TXN001" />
            </div>
          </div>

          {/* Row 2: type, direction */}
          <div className="form-row">
            <div className="form-group">
              <label>Type</label>
              <select value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
                <option value="deposit">Deposit</option>
                <option value="withdrawal">Withdrawal</option>
                <option value="transfer">Transfer</option>
                <option value="payment">Payment</option>
              </select>
            </div>
            <div className="form-group">
              <label>Direction</label>
              <select value={direction} onChange={(e) => setDirection(e.target.value)}>
                <option value="incoming">Incoming</option>
                <option value="outgoing">Outgoing</option>
              </select>
            </div>
          </div>

          {/* Row 3: amount, balance before, balance after */}
          <div className="form-row">
            <div className="form-group">
              <label>Amount (GHS)</label>
              <input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required placeholder="e.g. 500" />
            </div>
            <div className="form-group">
              <label>Balance Before</label>
              <input type="number" step="0.01" value={balanceBefore} onChange={(e) => setBalanceBefore(e.target.value)} placeholder="Optional" />
            </div>
            <div className="form-group">
              <label>Balance After</label>
              <input type="number" step="0.01" value={balanceAfter} onChange={(e) => setBalanceAfter(e.target.value)} placeholder="Optional" />
            </div>
          </div>

          {/* Row 4: time */}
          <div className="form-group">
            <label>Transaction Time</label>
            <input type="datetime-local" value={transactionTime} onChange={(e) => setTransactionTime(e.target.value)} required />
          </div>

          {/* Row 5: location, device */}
          <div className="form-row">
            <div className="form-group">
              <label>Location (optional)</label>
              <input type="text" value={locationInfo} onChange={(e) => setLocationInfo(e.target.value)} placeholder="e.g. Kumasi" />
            </div>
            <div className="form-group">
              <label>Device (optional)</label>
              <input type="text" value={deviceInfo} onChange={(e) => setDeviceInfo(e.target.value)} placeholder="e.g. Samsung A14" />
            </div>
          </div>

          <button type="submit" className="btn btn-primary" disabled={addLoading}>
            {addLoading ? "Submitting..." : "Add Transaction"}
          </button>
        </form>
      </div>

      {/* -------- Error state -------- */}
      {error && (
        <div className="message-box error">
          <span className="message-icon">❌</span>
          {error}
        </div>
      )}

      {/* -------- Loading state -------- */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading your transactions...</p>
        </div>
      )}

      {/* -------- Empty state -------- */}
      {!loading && !error && transactions.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">📋</div>
          <p>No transactions yet. Use the form above to add one.</p>
        </div>
      )}

      {/* -------- Transactions table -------- */}
      {transactions.length > 0 && (
        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Reference</th>
                <th>Type</th>
                <th>Direction</th>
                <th>Amount</th>
                <th>Before</th>
                <th>After</th>
                <th>Time</th>
                <th>Location</th>
                <th>Device</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t) => (
                <tr key={t.id}>
                  <td>{t.id}</td>
                  <td>{t.transaction_reference || "—"}</td>
                  <td>{t.transaction_type}</td>
                  <td>
                    <span className={`status-pill ${t.direction === "outgoing" ? "review" : "trusted"}`}>
                      {t.direction}
                    </span>
                  </td>
                  <td className="amount-cell">GHS {Number(t.amount).toFixed(2)}</td>
                  <td>{t.balance_before != null ? Number(t.balance_before).toFixed(2) : "—"}</td>
                  <td>{t.balance_after != null ? Number(t.balance_after).toFixed(2) : "—"}</td>
                  <td>{t.transaction_time || "—"}</td>
                  <td>{t.location_info || "—"}</td>
                  <td>{t.device_info || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}

export default Transactions;
