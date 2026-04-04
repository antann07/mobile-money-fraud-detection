import React, { useState } from "react";
import { useNavigate, Link, useSearchParams } from "react-router-dom";
import { API_BASE } from "../services/api";
import PasswordInput from "../components/PasswordInput";

function ResetPassword() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Token and email come from the reset link URL only.
  // They are never displayed in the UI or accepted from a manual input.
  const email = (searchParams.get("email") || "").trim();
  const token = (searchParams.get("token") || "").trim();

  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);

  // Guard: if the user landed here without a valid link, show a clear
  // actionable message right away rather than letting them fill the form.
  const missingParams = !email || !token;

  async function handleSubmit(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    if (missingParams) {
      setMessage("Reset link is missing required information. Please request a new link.");
      setMessageType("error");
      return;
    }
    if (newPassword.length < 8) {
      setMessage("Password must be at least 8 characters.");
      setMessageType("error");
      return;
    }
    if (!/[A-Z]/.test(newPassword) || !/[a-z]/.test(newPassword) || !/\d/.test(newPassword) || !/[^a-zA-Z0-9]/.test(newPassword)) {
      setMessage("Password needs uppercase, lowercase, digit, and a special character.");
      setMessageType("error");
      return;
    }
    if (newPassword !== confirmPassword) {
      setMessage("Passwords do not match.");
      setMessageType("error");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        // Trim both values — copy-paste or URL-decoding can introduce stray
        // whitespace that silently breaks the bcrypt token comparison.
        body: JSON.stringify({
          email: email.trim(),
          token: token.trim(),
          new_password: newPassword,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        setMessage(data.message || "Password reset successfully!");
        setMessageType("success");
        setTimeout(() => navigate("/login"), 2000);
      } else {
        const errors = data.errors || [
          "This reset link is invalid or has expired. Please request a new one.",
        ];
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[ResetPassword] Fetch failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🔑</div>
        <h1>Reset Password</h1>

        {/* Missing-link guard rendered before the form */}
        {missingParams ? (
          <div className="message-box error">
            <span className="message-icon">❌</span>
            This reset link is incomplete or has already been used.
            <p style={{ marginTop: "0.5rem", fontSize: "0.875rem" }}>
              <Link to="/forgot-password">Request a new password reset link.</Link>
            </p>
          </div>
        ) : (
          <>
            <p>Enter your new password below.</p>

            {message && (
              <div className={`message-box ${messageType}`}>
                <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
                {message}
                {messageType === "error" && (
                  <p style={{ marginTop: "0.5rem", fontSize: "0.875rem" }}>
                    Need a new link?{" "}
                    <Link to="/forgot-password">Request a password reset.</Link>
                  </p>
                )}
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label htmlFor="reset-new-password">New Password</label>
                <PasswordInput
                  id="reset-new-password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Upper + lower + digit + special"
                  autoComplete="new-password"
                />
              </div>

              <div className="form-group">
                <label htmlFor="reset-confirm-password">Confirm Password</label>
                <PasswordInput
                  id="reset-confirm-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat your new password"
                  autoComplete="new-password"
                />
              </div>

              <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
                {loading ? "Resetting..." : "Reset Password"}
              </button>
            </form>
          </>
        )}

        <p className="auth-footer">
          <Link to="/login">Back to Sign In</Link>
        </p>
      </div>
    </div>
  );
}

export default ResetPassword;
