import React, { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { publicFetch, authFetch } from "../services/api";
import PageLayout from "../components/PageLayout";
import { VERDICT_LABEL, pillClass } from "../utils/verdictUtils";
import { relativeTime } from "../utils/timeUtils";

// ============================================================
// Dashboard.jsx — Wallet Protection Dashboard
// ============================================================
// Fetches on mount:
//   GET /api/health                    — backend connection check
//   GET /api/wallet                    — count wallets
//   GET /api/message-checks/history    — message check stats + recent list
//
// GET requests are automatically deduplicated and short-cached by
// api.js (20-second TTL), so navigating Dashboard → MessageHistory
// reuses the same in-memory data rather than firing a second request.
// ============================================================

function Dashboard() {
  const [healthOk, setHealthOk] = useState(null);
  const [stats, setStats] = useState({
    wallets: 0,
    totalChecks: 0,
    verified: 0,
    flagged: 0,
    recentChecks: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Guard against stale state updates from unmounted instances.
  // In React StrictMode (development), useEffect fires twice per mount.
  // The mountedRef lets async callbacks know whether to proceed with
  // setState after the first invocation has been cleaned up.
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    checkHealth();
    loadStats();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function checkHealth() {
    try {
      await publicFetch("/health");
      if (mountedRef.current) setHealthOk(true);
    } catch {
      if (mountedRef.current) setHealthOk(false);
    }
  }

  async function loadStats() {
    const token = localStorage.getItem("token");
    if (!token) {
      if (mountedRef.current) setLoading(false);
      return;
    }

    try {
      const [walletRes, historyRes] = await Promise.all([
        authFetch("/wallet"),
        authFetch("/message-checks/history"),
      ]);

      if (!mountedRef.current) return; // unmounted before both resolved

      if (!walletRes.response.ok || !historyRes.response.ok) {
        if (historyRes.response.status === 429 || walletRes.response.status === 429) {
          // Silently degrade — show zeros rather than an alarming error banner
          // The user will see the proper 429 experience on the History page
        } else {
          setError("Some data could not be loaded. Try logging in again.");
        }
      }

      const walletCount = walletRes.data.wallets?.length || 0;
      const checks = historyRes.data.data || [];
      const totalChecks = checks.length;

      const verified = checks.filter(
        (c) => c.prediction_summary?.predicted_label === "genuine"
      ).length;

      const flagged = checks.filter(
        (c) =>
          c.prediction_summary?.predicted_label === "suspicious" ||
          c.prediction_summary?.predicted_label === "likely_fraudulent"
      ).length;

      // Most-recent 5 checks, newest first
      const recentChecks = [...checks]
        .sort((a, b) => {
          const da = new Date(a.message_check?.created_at || 0);
          const db = new Date(b.message_check?.created_at || 0);
          return db - da;
        })
        .slice(0, 5);

      setStats({ wallets: walletCount, totalChecks, verified, flagged, recentChecks });
    } catch (err) {
      if (!mountedRef.current) return;
      console.error("[Dashboard] Failed to load stats:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      if (mountedRef.current) setLoading(false);
    }
  }

  // Derived display values (safe when not yet loaded)
  const clearPct = stats.totalChecks > 0
    ? Math.round((stats.verified / stats.totalChecks) * 100)
    : 0;
  const clearColor = clearPct >= 80
    ? "var(--color-success)"
    : clearPct >= 60
    ? "var(--color-warning)"
    : "var(--color-danger)";

  // Personalized greeting from stored user object
  const username = (() => {
    try {
      const user = JSON.parse(localStorage.getItem("user"));
      return user?.username?.trim() || null;
    } catch { return null; }
  })();

  const greeting = username ? `Welcome back, ${username}` : "Welcome";

  return (
    <PageLayout
      title={greeting}
      subtitle="Your wallet protection overview — wallets, verifications, and alerts at a glance."
    >

      {/* Backend connection — only surface an error if it actually fails */}
      {healthOk === false && (
        <div className="message-box error" role="alert" aria-live="assertive">
          <span className="message-icon">&#10060;</span>
          The protection service is currently unavailable. Please try again shortly.
        </div>
      )}

      {/* Login prompt if no token */}
      {!localStorage.getItem("token") && (
        <div className="message-box info" role="status">
          <span className="message-icon">&#128273;</span>
          Log in to see your live dashboard stats.
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="message-box error" role="alert" aria-live="assertive">
          <span className="message-icon">&#10060;</span>
          {error}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="loading-state" role="status" aria-live="polite" aria-label="Loading dashboard statistics">
          <div className="spinner" aria-hidden="true"></div>
          <p>Loading your dashboard&hellip;</p>
        </div>
      ) : (
        <>
          {/* ── Flagged-messages attention callout ─────────────────── */}
          {stats.flagged > 0 && (
            <div className="message-box warning dash-flagged-callout" role="alert">
              <span className="message-icon">&#9888;&#65039;</span>
              <div>
                <strong>
                  {stats.flagged} message{stats.flagged > 1 ? "s" : ""} flagged for review.
                </strong>
                {" "}Do not act on flagged messages until you have confirmed them.{" "}
                <Link to="/message-history" className="dash-inline-link">
                  Review now &rarr;
                </Link>
              </div>
            </div>
          )}

          {/* ── KPI cards ──────────────────────────────────────────── */}
          <section aria-label="Account summary statistics">
            <div className="summary-grid">

              <Link to="/wallets" className="summary-card summary-card-link" aria-label="Manage Wallets">
                <div className="card-header">
                  <div>
                    <h3>Linked Wallets</h3>
                    <div className="summary-value">{stats.wallets}</div>
                    <p className="summary-note">MoMo accounts linked</p>
                  </div>
                  <div className="card-icon-bg blue">&#128179;</div>
                </div>
              </Link>

              <Link to="/message-history" className="summary-card summary-card-link" aria-label="View message history">
                <div className="card-header">
                  <div>
                    <h3>Messages Checked</h3>
                    <div className="summary-value">{stats.totalChecks}</div>
                    <p className="summary-note">Total verifications run</p>
                  </div>
                  <div className="card-icon-bg amber">&#128232;</div>
                </div>
              </Link>

              <Link to="/message-history" className="summary-card summary-card-link" aria-label="View verified messages">
                <div className="card-header">
                  <div>
                    <h3>Confirmed Genuine</h3>
                    <div className="summary-value">{stats.verified}</div>
                    <p className="summary-note">Verified authentic</p>
                  </div>
                  <div className="card-icon-bg green">&#128737;&#65039;</div>
                </div>
              </Link>

              <Link to="/message-history" className="summary-card summary-card-link" aria-label="Review flagged messages">
                <div className="card-header">
                  <div>
                    <h3>Flagged</h3>
                    <div className={`summary-value${stats.flagged > 0 ? " danger-text" : ""}`}>
                      {stats.flagged}
                    </div>
                    <p className="summary-note">Needs review</p>
                  </div>
                  <div className="card-icon-bg red">&#9888;&#65039;</div>
                </div>
              </Link>

            </div>
          </section>

          {/* ── Widgets row (only when checks exist) ───────────────── */}
          {stats.totalChecks > 0 && (
            <div className="dash-widgets-row">

              {/* Security overview */}
              <div className="form-card dash-widget-card">
                <h3 className="dash-widget-title">Security Overview</h3>

                <div className="dash-meter-row">
                  <div className="dash-meter-label">
                    <span>Clear rate</span>
                    <span className="dash-meter-pct" style={{ color: clearColor }}>
                      {clearPct}%
                    </span>
                  </div>
                  <div className="dash-meter-track" role="progressbar" aria-valuenow={clearPct} aria-valuemin={0} aria-valuemax={100}>
                    <div
                      className="dash-meter-fill"
                      style={{ width: `${clearPct}%`, background: clearColor }}
                    />
                  </div>
                  <p className="dash-meter-sub">
                    of checked messages confirmed genuine by the fraud engine
                  </p>
                </div>

                <div className="dash-ov-stats">
                  <div className="dash-ov-item">
                    <span className="dash-ov-value">{stats.totalChecks}</span>
                    <span className="dash-ov-label">Total checked</span>
                  </div>
                  <div className="dash-ov-item">
                    <span className="dash-ov-value" style={{ color: "var(--color-success)" }}>
                      {stats.verified}
                    </span>
                    <span className="dash-ov-label">Verified clean</span>
                  </div>
                  {stats.flagged > 0 && (
                    <div className="dash-ov-item">
                      <span className="dash-ov-value" style={{ color: "var(--color-danger)" }}>
                        {stats.flagged}
                      </span>
                      <span className="dash-ov-label">Flagged</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Quick actions */}
              <div className="form-card dash-widget-card dash-quick-actions">
                <h3 className="dash-widget-title">Quick Actions</h3>
                <div className="dash-action-list">
                  <Link to="/check-message" className="btn btn-primary dash-action-btn">
                    Verify a Message
                  </Link>
                  <Link to="/wallets" className="btn btn-outline dash-action-btn">
                    My Wallets
                  </Link>
                  <Link to="/message-history" className="btn btn-outline dash-action-btn">
                    View Full History
                  </Link>
                </div>
              </div>

            </div>
          )}

          {/* ── Recent checks ──────────────────────────────────────── */}
          {stats.totalChecks > 0 && (
            <section className="dash-recent-section" aria-label="Recent message checks">
              <div className="dash-section-head">
                <h3 className="dash-section-title">Recent Checks</h3>
                <Link to="/message-history" className="dash-view-all">
                  View all &rarr;
                </Link>
              </div>

              <div className="form-card dash-recent-card">
                {stats.recentChecks.map((item) => {
                  const mc = item.message_check;
                  const ps = item.prediction_summary;
                  const label = ps?.predicted_label;
                  const sender =
                    mc.sender_name ||
                    mc.counterparty_name ||
                    mc.sender_number ||
                    mc.counterparty_number;
                  const verdictDisplay = label
                    ? (VERDICT_LABEL[label] || label.replace(/_/g, " "))
                    : "Not Analysed";
                  const pillCls = label ? pillClass(label) : "info";

                  return (
                    <Link
                      to={`/message-history/${mc.id}`}
                      key={mc.id}
                      className="dash-recent-row"
                    >
                      <span className={`status-pill ${pillCls} dash-recent-pill`}>
                        {verdictDisplay}
                      </span>
                      <span className="dash-recent-sender">
                        {sender || <span className="dash-recent-unknown">Unknown sender</span>}
                      </span>
                      {mc.amount != null && (
                        <span className="dash-recent-amount">
                          {mc.currency || "GHS"}&nbsp;{Number(mc.amount).toLocaleString()}
                        </span>
                      )}
                      <span className="dash-recent-time">
                        {relativeTime(mc.created_at).label}
                      </span>
                    </Link>
                  );
                })}
              </div>
            </section>
          )}

          {/* ── Empty state nudge (no checks yet) ─────────────────── */}
          {stats.totalChecks === 0 && localStorage.getItem("token") && (
            <div className="dash-empty-nudge">
              <div className="dash-nudge-icon">&#128737;&#65039;</div>
              <h3>Start protecting your wallet</h3>
              <p>
                Verify your first MoMo message to build your protection history
                and let the fraud engine analyse your payment notifications.
              </p>
              <div className="dash-nudge-actions">
                <Link to="/check-message" className="btn btn-primary">
                  Verify a Message
                </Link>
                {stats.wallets === 0 && (
                  <Link to="/wallets" className="btn btn-outline">
                    Link a Wallet First
                  </Link>
                )}
              </div>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}

export default Dashboard;