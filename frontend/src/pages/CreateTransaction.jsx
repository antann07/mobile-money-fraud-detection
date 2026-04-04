import React, { useState, useEffect } from "react";
import { authFetch } from "../services/api";

// ============================================================
// CreateTransaction.jsx — Record a new transaction (Phase 3)
// ============================================================
// Routes used:
//   GET  /api/wallet             — load wallets for the dropdown
//   POST /api/transactions/add   — submit transaction (auto fraud scored)
// ============================================================

function CreateTransaction() {
  // Form fields
  const [walletId, setWalletId] = useState("");
  const [transactionType, setTransactionType] = useState("deposit");
  const [direction, setDirection] = useState("incoming");
  const [amount, setAmount] = useState("");
  const [balanceBefore, setBalanceBefore] = useState("");
  const [balanceAfter, setBalanceAfter] = useState("");
  const [transactionTime, setTransactionTime] = useState("");
  const [locationInfo, setLocationInfo] = useState("");
  const [deviceInfo, setDeviceInfo] = useState("");

  // UI state
  const [wallets, setWallets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [prediction, setPrediction] = useState(null);

  useEffect(() => {
    loadWallets();
  }, []);

  async function loadWallets() {
    try {
      const { data, response } = await authFetch("/api/wallet");
      if (response.ok) {
        setWallets(data.wallets || []);
        if (data.wallets?.length > 0) {
          setWalletId(String(data.wallets[0].id));
        }
      }
    } catch (err) {
      console.error("[CreateTransaction] Could not load wallets:", err);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");
    setPrediction(null);

    const token = localStorage.getItem("token");
    if (!token) {
      setMessage("You must log in first.");
      setMessageType("error");
      return;
    }

    setLoading(true);

    const payload = {
      wallet_id: Number(walletId),
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
      const { data, response } = await authFetch("/api/transactions/add", "POST", payload);

      if (response.status === 201) {
        setMessage("Transaction added and scored successfully!");
        setMessageType("success");
        setPrediction(data.prediction);
        // Reset form
        setAmount("");
        setBalanceBefore("");
        setBalanceAfter("");
        setTransactionTime("");
        setLocationInfo("");
        setDeviceInfo("");
      } else if (response.status === 401) {
        setMessage("Session expired. Please log in again.");
        setMessageType("error");
      } else if (response.status === 403) {
        setMessage("Wallet does not belong to you. Select a valid wallet.");
        setMessageType("error");
      } else {
        const errors = data.errors || ["Failed to add transaction."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : errors);
        setMessageType("error");
      }
    } catch (err) {
      console.error("[CreateTransaction] Fetch failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 600, margin: "40px auto", padding: 24 }}>
      <h2 style={{ marginBottom: 24 }}>Record a Transaction</h2>

      {message && (
        <div
          style={{
            padding: 12,
            marginBottom: 16,
            borderRadius: 6,
            background: messageType === "success" ? "#d4edda" : "#f8d7da",
            color: messageType === "success" ? "#155724" : "#721c24",
          }}
        >
          {message}
        </div>
      )}

      {/* Fraud prediction result */}
      {prediction && (
        <div
          style={{
            padding: 16,
            marginBottom: 20,
            borderRadius: 8,
            background: prediction.risk_level === "high" ? "#fef2f2"
              : prediction.risk_level === "medium" ? "#fffbeb" : "#f0fdf4",
            border: `1px solid ${
              prediction.risk_level === "high" ? "#fecaca"
                : prediction.risk_level === "medium" ? "#fde68a" : "#bbf7d0"
            }`,
          }}
        >
          <strong>Fraud Prediction:</strong> {prediction.prediction} —{" "}
          <strong>Risk:</strong> {prediction.risk_level}
          <br />
          <small>{prediction.explanation}</small>
        </div>
      )}

      <div style={{ background: "#f9fafb", padding: 20, borderRadius: 8 }}>
        <form onSubmit={handleSubmit}>
          {/* Wallet selector */}
          <div style={{ marginBottom: 14 }}>
            <label>Wallet</label>
            {wallets.length === 0 ? (
              <p style={{ color: "#888", fontSize: 14 }}>
                No wallets found. Link one on the Wallets page first.
              </p>
            ) : (
              <select value={walletId} onChange={(e) => setWalletId(e.target.value)} style={inputStyle}>
                {wallets.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.provider} — {w.wallet_number} ({w.wallet_name})
                  </option>
                ))}
              </select>
            )}
          </div>

          {/* Type and direction */}
          <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
            <div style={{ flex: 1 }}>
              <label>Type</label>
              <select value={transactionType} onChange={(e) => setTransactionType(e.target.value)} style={inputStyle}>
                <option value="deposit">Deposit</option>
                <option value="withdrawal">Withdrawal</option>
                <option value="transfer">Transfer</option>
                <option value="payment">Payment</option>
              </select>
            </div>
            <div style={{ flex: 1 }}>
              <label>Direction</label>
              <select value={direction} onChange={(e) => setDirection(e.target.value)} style={inputStyle}>
                <option value="incoming">Incoming</option>
                <option value="outgoing">Outgoing</option>
              </select>
            </div>
          </div>

          {/* Amount */}
          <div style={{ marginBottom: 14 }}>
            <label>Amount (GHS)</label>
            <input type="number" step="0.01" min="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required style={inputStyle} placeholder="e.g. 500" />
          </div>

          {/* Balance before / after */}
          <div style={{ display: "flex", gap: 12, marginBottom: 14 }}>
            <div style={{ flex: 1 }}>
              <label>Balance Before</label>
              <input type="number" step="0.01" value={balanceBefore} onChange={(e) => setBalanceBefore(e.target.value)} style={inputStyle} placeholder="Optional" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Balance After</label>
              <input type="number" step="0.01" value={balanceAfter} onChange={(e) => setBalanceAfter(e.target.value)} style={inputStyle} placeholder="Optional" />
            </div>
          </div>

          {/* Transaction time */}
          <div style={{ marginBottom: 14 }}>
            <label>Transaction Time</label>
            <input type="datetime-local" value={transactionTime} onChange={(e) => setTransactionTime(e.target.value)} required style={inputStyle} />
          </div>

          {/* Location and device */}
          <div style={{ display: "flex", gap: 12, marginBottom: 20 }}>
            <div style={{ flex: 1 }}>
              <label>Location (optional)</label>
              <input type="text" value={locationInfo} onChange={(e) => setLocationInfo(e.target.value)} style={inputStyle} placeholder="e.g. Kumasi" />
            </div>
            <div style={{ flex: 1 }}>
              <label>Device (optional)</label>
              <input type="text" value={deviceInfo} onChange={(e) => setDeviceInfo(e.target.value)} style={inputStyle} placeholder="e.g. Samsung A14" />
            </div>
          </div>

          <button type="submit" disabled={loading || wallets.length === 0} style={buttonStyle}>
            {loading ? "Submitting..." : "Submit Transaction"}
          </button>
        </form>
      </div>
    </div>
  );
}

const inputStyle = {
  width: "100%",
  padding: 10,
  marginTop: 4,
  borderRadius: 6,
  border: "1px solid #ccc",
  fontSize: 14,
  boxSizing: "border-box",
};

const buttonStyle = {
  width: "100%",
  padding: 12,
  background: "#2563eb",
  color: "#fff",
  border: "none",
  borderRadius: 6,
  fontSize: 16,
  cursor: "pointer",
};

export default CreateTransaction;
