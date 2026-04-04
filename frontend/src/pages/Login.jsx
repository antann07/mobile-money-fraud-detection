import React, { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { API_BASE } from "../services/api";
import PasswordInput from "../components/PasswordInput";

function Login() {
  const navigate = useNavigate();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleLogin(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    if (!identifier.trim()) {
      setMessage("Email or username is required.");
      setMessageType("error");
      return;
    }
    if (password.length < 1) {
      setMessage("Password is required.");
      setMessageType("error");
      return;
    }

    setLoading(true);
    const url = `${API_BASE}/api/auth/login`;

    // Send the correct key so the backend receives either {email:…} or {username:…}.
    // The backend accepts both — this keeps the payload semantically correct.
    const trimmed = identifier.trim();
    const isEmail = trimmed.includes("@");
    const payload = isEmail
      ? { email: trimmed, password }
      : { username: trimmed, password };

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (response.ok) {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
        if (data.token) localStorage.setItem("token", data.token);
        if (data.user) localStorage.setItem("user", JSON.stringify(data.user));
        setMessage("Login successful! Redirecting...");
        setMessageType("success");
        setTimeout(() => { navigate("/dashboard"); window.location.reload(); }, 800);
      } else if (response.status === 429) {
        const errors = data.errors || ["Too many attempts. Please wait."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      } else if (response.status === 401) {
        const errors = data.errors || ["Invalid credentials."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      } else {
        const errors = data.errors || data.message || "Login failed.";
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Login] Fetch failed:", err);
      setMessage("Could not reach the server. Is the backend running?");
      setMessageType("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-logo">🛡️</div>
        <h1>Welcome Back</h1>
        <p>Sign in to access your fraud detection dashboard.</p>

        {message && (
          <div className={`message-box ${messageType}`} role="alert" aria-live="assertive">
            <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
            {message}
          </div>
        )}

        <form onSubmit={handleLogin}>
          <div className="form-group">
            <label htmlFor="login-identifier">Email or Username</label>
            <input
              id="login-identifier"
              type="text"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              required
              autoComplete="username"
              placeholder="e.g. kwame@example.com or kwame"
              aria-required="true"
            />
          </div>

          <div className="form-group">
            <label htmlFor="login-password">Password</label>
            <PasswordInput
              id="login-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
              autoComplete="current-password"
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p className="auth-footer">
          <Link to="/forgot-password">Forgot password?</Link>
        </p>
        <p className="auth-footer" style={{ marginTop: "0.5rem" }}>
          Don't have an account? <Link to="/register">Register here</Link>
        </p>
      </div>
    </div>
  );
}

export default Login;