import React, { useState, useEffect } from "react";
import { authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";

// ============================================================
// Wallets.jsx — Link and manage mobile money wallets
// ============================================================
// Routes used:
//   GET    /api/wallet                    — list all linked wallets
//   POST   /api/wallet/add               — link a new wallet
//   PATCH  /api/wallet/<id>/primary      — set as primary
//   DELETE /api/wallet/<id>              — remove a wallet
// ============================================================

// Mask wallet number: 024 *** 4567
function maskNumber(n) {
  if (!n || n.length < 7) return n;
  return `${n.slice(0, 3)} *** ${n.slice(-4)}`;
}

const PROVIDER_CLASSES = {
  MTN: "wallet-provider-mtn",
  Telecel: "wallet-provider-telecel",
  AirtelTigo: "wallet-provider-airteltigo",
};

function Wallets() {
  // --- Form state ---
  const [walletNumber, setWalletNumber] = useState("");
  const [provider, setProvider] = useState("MTN");
  const [walletName, setWalletName] = useState("");
  const [isPrimary, setIsPrimary] = useState(false);

  // --- List state ---
  const [wallets, setWallets] = useState([]);
  const [loading, setLoading] = useState(true);

  // --- UI feedback ---
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState(""); // "success" | "error"
  const [addLoading, setAddLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(null); // wallet id being acted on

  // --- Remove confirm ---
  const [confirmRemoveId, setConfirmRemoveId] = useState(null);

  // -------- Fetch wallets on mount --------
  useEffect(() => {
    fetchWallets();
  }, []);

  async function fetchWallets() {
    const token = localStorage.getItem("token");
    if (!token) {
      setMessage("You must log in first to view wallets.");
      setMessageType("error");
      setLoading(false);
      return;
    }

    setLoading(true);
    try {
      const { data, response } = await authFetch("/wallet");

      if (response.ok) {
        setWallets(data.wallets || []);
      } else if (response.status === 401) {
        setMessage("Session expired. Please log in again.");
        setMessageType("error");
      } else {
        setMessage(parseErrors(data, "Failed to load wallets."));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Wallets] Fetch failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  // -------- Add wallet --------
  async function handleAddWallet(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    const token = localStorage.getItem("token");
    if (!token) {
      setMessage("You must log in first to add a wallet.");
      setMessageType("error");
      return;
    }

    setAddLoading(true);

    // --- Client-side validation ---
    if (!/^\d{10}$/.test(walletNumber)) {
      setMessage("Wallet number must be exactly 10 digits.");
      setMessageType("error");
      setAddLoading(false);
      return;
    }
    if (walletName.trim().length < 2) {
      setMessage("Wallet name must be at least 2 characters.");
      setMessageType("error");
      setAddLoading(false);
      return;
    }

    try {
      const { data, response } = await authFetch("/wallet/add", "POST", {
        wallet_number: walletNumber,
        provider,
        wallet_name: walletName,
        is_primary: isPrimary,
      });

      if (response.status === 201) {
        setMessage("Wallet linked successfully!");
        setMessageType("success");
        setWalletNumber("");
        setWalletName("");
        setIsPrimary(false);
        fetchWallets();
      } else if (response.status === 401) {
        setMessage("Session expired. Please log in again.");
        setMessageType("error");
      } else if (response.status === 409) {
        setMessage(parseErrors(data, "This wallet is already registered."));
        setMessageType("error");
      } else {
        setMessage(parseErrors(data, "Failed to add wallet."));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Wallets] Add failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setAddLoading(false);
    }
  }

  // -------- Set primary --------
  async function handleSetPrimary(walletId) {
    setActionLoading(walletId);
    setMessage("");
    try {
      const { data, response } = await authFetch(`/wallet/${walletId}/primary`, "PATCH");
      if (response.ok) {
        setWallets(data.wallets || []);
        setMessage("Primary wallet updated.");
        setMessageType("success");
      } else {
        setMessage(parseErrors(data, "Failed to update primary wallet."));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Wallets] Set-primary failed:", err);
      setMessage("Could not reach the server.");
      setMessageType("error");
    } finally {
      setActionLoading(null);
    }
  }

  // -------- Remove --------
  async function handleRemove(walletId) {
    setConfirmRemoveId(null);
    setActionLoading(walletId);
    setMessage("");
    try {
      const { data, response } = await authFetch(`/wallet/${walletId}`, "DELETE");
      if (response.ok) {
        setWallets((prev) => prev.filter((w) => w.id !== walletId));
        setMessage("Wallet removed.");
        setMessageType("success");
      } else {
        setMessage(parseErrors(data, "Failed to remove wallet."));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Wallets] Remove failed:", err);
      setMessage("Could not reach the server.");
      setMessageType("error");
    } finally {
      setActionLoading(null);
    }
  }

  // Helper: extract error string from response data
  function parseErrors(data, fallback) {
    const errors = data.errors || data.message;
    if (Array.isArray(errors)) return errors.join(" ");
    if (typeof errors === "string") return errors;
    return fallback;
  }

  return (
    <PageLayout
      title="My Wallets"
      subtitle="Link your mobile money wallets to monitor transactions and detect fraud."
    >
      <div className="wallets-page-inner">

      {/* Feedback message */}
      {message && (
        <div
          className={`message-box ${messageType}`}
          role={messageType === "error" ? "alert" : "status"}
          aria-live={messageType === "error" ? "assertive" : "polite"}
        >
          <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
          {message}
        </div>
      )}

      {/* -------- Add Wallet Form -------- */}
      <div className="form-card wallet-form-card">
        <h3>Link a New Wallet</h3>
        <form onSubmit={handleAddWallet} noValidate>

          {/* Row 1: Number + Provider side by side */}
          <div className="wallet-form-grid">
            <div className="form-group">
              <label htmlFor="wallet-number">Wallet Number</label>
              <input
                id="wallet-number"
                type="text"
                value={walletNumber}
                onChange={(e) => setWalletNumber(e.target.value)}
                required
                autoComplete="tel-national"
                inputMode="numeric"
                placeholder="e.g. 0241234567"
                aria-required="true"
              />
            </div>

            <div className="form-group">
              <label htmlFor="wallet-provider">Provider</label>
              <select
                id="wallet-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
              >
                <option value="MTN">MTN MoMo</option>
                <option value="Telecel">Telecel Cash</option>
                <option value="AirtelTigo">AirtelTigo Money</option>
              </select>
            </div>
          </div>

          {/* Row 2: Wallet Name full width */}
          <div className="form-group">
            <label htmlFor="wallet-name">
              Display Name
              <span className="form-label-hint">shown in your wallet list</span>
            </label>
            <input
              id="wallet-name"
              type="text"
              value={walletName}
              onChange={(e) => setWalletName(e.target.value)}
              required
              autoComplete="off"
              placeholder="e.g. My MTN MoMo"
              aria-required="true"
            />
          </div>

          {/* Row 3: Checkbox */}
          <div className="form-group wallet-checkbox-row">
            <label className="checkbox-label" htmlFor="wallet-primary">
              <input
                id="wallet-primary"
                type="checkbox"
                checked={isPrimary}
                onChange={(e) => setIsPrimary(e.target.checked)}
              />
              <span>
                Set as primary wallet
                <span className="checkbox-hint">Used by default for fraud checks</span>
              </span>
            </label>
          </div>

          {/* Form footer: security note + submit button */}
          <div className="wallet-form-footer">
            <p className="form-security-note">
              🔒 Wallet numbers are stored encrypted and used only for fraud monitoring.
            </p>
            <button
              type="submit"
              className="btn btn-primary wallet-submit-btn"
              disabled={addLoading}
            >
              {addLoading ? "Linking…" : "Link Wallet"}
            </button>
          </div>
        </form>
      </div>

      {/* -------- Linked Wallets -------- */}
      <div className="wallets-section-header">
        <h3 className="section-title wallets-section-title">
          Linked Wallets
          {wallets.length > 0 && (
            <span className="section-count wallets-count">{wallets.length}</span>
          )}
        </h3>
      </div>

      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading your wallets…</p>
        </div>
      )}

      {!loading && wallets.length === 0 && (
        <div className="empty-state">
          <div className="empty-state-icon">👛</div>
          <p>No wallets linked yet.</p>
          <p>Use the form above to add your first wallet.</p>
        </div>
      )}

      {wallets.length > 0 && (
        <div className="wallet-card-list">
          {wallets.map((w) => {
            const isBusy = actionLoading === w.id;
            const isConfirming = confirmRemoveId === w.id;
            return (
              <div
                key={w.id}
                className={`wallet-card${w.is_primary ? " wallet-card--primary" : ""}`}
                aria-label={`${w.wallet_name} wallet`}
              >
                {/* Left: identity block */}
                <div className="wallet-card-body">
                  {/* Row 1: display name + primary badge */}
                  <div className="wallet-card-name-row">
                    <span className="wallet-card-name">{w.wallet_name}</span>
                    {w.is_primary && (
                      <span className="status-pill trusted wallet-primary-badge">Primary</span>
                    )}
                  </div>
                  {/* Row 2: provider chip + masked number */}
                  <div className="wallet-card-sub-row">
                    <span className={`wallet-provider-chip ${PROVIDER_CLASSES[w.provider] || ""}`}>
                      {w.provider}
                    </span>
                    <span
                      className="wallet-card-number"
                      aria-label={`Wallet number ending ${w.wallet_number.slice(-4)}`}
                    >
                      {maskNumber(w.wallet_number)}
                    </span>
                  </div>
                </div>

                {/* Right: action panel */}
                <div className="wallet-card-actions">
                  {isConfirming ? (
                    <div className="wallet-confirm-remove">
                      <span className="wallet-confirm-text">Remove this wallet?</span>
                      <button
                        className="btn-danger-ghost"
                        onClick={() => handleRemove(w.id)}
                        disabled={isBusy}
                      >
                        {isBusy ? "Removing…" : "Yes, Remove"}
                      </button>
                      <button
                        className="btn-ghost"
                        onClick={() => setConfirmRemoveId(null)}
                        disabled={isBusy}
                      >
                        Cancel
                      </button>
                    </div>
                  ) : (
                    <>
                      {!w.is_primary && (
                        <button
                          className="btn-ghost"
                          onClick={() => handleSetPrimary(w.id)}
                          disabled={isBusy}
                          aria-label={`Set ${w.wallet_name} as primary wallet`}
                        >
                          {isBusy ? "Updating…" : "Set Primary"}
                        </button>
                      )}
                      <button
                        className="btn-danger-ghost"
                        onClick={() => setConfirmRemoveId(w.id)}
                        disabled={isBusy}
                        aria-label={`Remove ${w.wallet_name}`}
                      >
                        Remove
                      </button>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>{/* end wallets-page-inner */}
    </PageLayout>
  );
}

export default Wallets;
