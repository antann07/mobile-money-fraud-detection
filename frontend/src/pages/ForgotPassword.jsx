import React, { useState } from "react";
import { Link } from "react-router-dom";
import { API_BASE } from "../services/api";

function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setMessage("Please enter a valid email address.");
      setMessageType("error");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/auth/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim() }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message || "If that email is registered, a reset link has been sent.");
        setMessageType("success");
      } else {
        const errors = data.errors || ["Request failed."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[ForgotPassword] Fetch failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🔐</div>
        <h1>Forgot Password</h1>
        <p>Enter your email and we'll send you a reset link.</p>

        {message && (
          <div className={`message-box ${messageType}`}>
            <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
            {message}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label>Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              placeholder="e.g. kwame@example.com"
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "Sending..." : "Send Reset Link"}
          </button>
        </form>

        <p className="auth-footer">
          Remember your password? <Link to="/login">Sign in here</Link>
        </p>
      </div>
    </div>
  );
}

export default ForgotPassword;
