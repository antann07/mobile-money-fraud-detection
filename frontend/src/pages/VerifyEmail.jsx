import React, { useState, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { API_BASE } from "../services/api";

function VerifyEmail() {
  const [searchParams] = useSearchParams();
  const email = (searchParams.get("email") || "").trim();
  const token = (searchParams.get("token") || "").trim();

  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);
  const [verified, setVerified] = useState(false);

  const missingParams = !email || !token;

  useEffect(() => {
    if (missingParams) return;

    async function doVerify() {
      setLoading(true);
      try {
        const response = await fetch(`${API_BASE}/auth/verify-email`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ email: email.trim(), token: token.trim() }),
        });

        const data = await response.json();

        if (response.ok && data.success) {
          setMessage(data.message || "Email verified successfully!");
          setMessageType("success");
          setVerified(true);
        } else {
          const errors = data.errors || ["Verification failed."];
          setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
          setMessageType("error");
        }
      } catch (err) {
        console.error("[VerifyEmail] Fetch failed:", err);
        setMessage("Could not reach the server. Is the backend running?");
        setMessageType("error");
      } finally {
        setLoading(false);
      }
    }

    doVerify();
  }, [email, token, missingParams]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">📧</div>
        <h1>Email Verification</h1>

        {missingParams ? (
          <div className="message-box error">
            <span className="message-icon">❌</span>
            This verification link is incomplete or invalid.
            <p style={{ marginTop: "0.5rem", fontSize: "0.875rem" }}>
              <Link to="/login">Go to Sign In</Link>
            </p>
          </div>
        ) : loading ? (
          <p>Verifying your email...</p>
        ) : (
          <>
            {message && (
              <div className={`message-box ${messageType}`}>
                <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
                {message}
              </div>
            )}

            {verified ? (
              <p style={{ textAlign: "center", marginTop: "1rem" }}>
                <Link to="/login" className="btn btn-primary auth-btn" style={{ display: "inline-block", textDecoration: "none" }}>
                  Sign In to Your Account
                </Link>
              </p>
            ) : messageType === "error" && (
              <p style={{ textAlign: "center", marginTop: "1rem", fontSize: "0.875rem" }}>
                <Link to="/login">Go to Sign In</Link>
              </p>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default VerifyEmail;
