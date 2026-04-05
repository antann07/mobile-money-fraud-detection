import React, { useState, useRef } from "react";
import { useNavigate, Link } from "react-router-dom";
import { API_BASE } from "../services/api";
import PasswordInput from "../components/PasswordInput";

function Register() {
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState("");
  const [loading, setLoading] = useState(false);
  const messageRef = useRef(null);

  // Scroll the error banner into view and announce it to screen readers.
  function showError(msg) {
    setMessage(msg);
    setMessageType("error");
    // Deferred so the DOM update completes before scrolling
    setTimeout(() => messageRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 50);
  }

  async function handleRegister(e) {
    e.preventDefault();
    setMessage("");
    setMessageType("");

    if (fullName.trim().length < 2) {
      showError("Full name must be at least 2 characters.");
      return;
    }
    if (username && !/^[a-zA-Z][a-zA-Z0-9._-]{2,29}$/.test(username)) {
      showError("Username must be 3-30 chars, start with a letter (letters, digits, . - _ ).");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      showError("Please enter a valid email address.");
      return;
    }
    if (!/^\d{10}$/.test(phone)) {
      showError("Phone number must be exactly 10 digits (e.g. 0241234567).");
      return;
    }
    if (password.length < 8) {
      showError("Password must be at least 8 characters.");
      return;
    }
    if (!/[A-Z]/.test(password) || !/[a-z]/.test(password) || !/\d/.test(password) || !/[^a-zA-Z0-9]/.test(password)) {
      showError("Password needs uppercase, lowercase, digit, and a special character.");
      return;
    }

    setLoading(true);
    const url = `${API_BASE}/auth/register`;
    const payload = {
      full_name: fullName,
      username: username || undefined,
      email,
      phone_number: phone,
      password,
    };

    try {
      const response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (response.status === 201 || response.ok) {
        if (data.token) localStorage.setItem("token", data.token);
        if (data.user) localStorage.setItem("user", JSON.stringify(data.user));

        if (data.email_verification_required) {
          setMessage(data.message || "Registration successful! Please check your email to verify your account.");
          setMessageType("success");
          // Don't auto-redirect — user needs to verify email first
        } else {
          setMessage(data.message || "Registration successful! A welcome email has been sent. Redirecting to dashboard...");
          setMessageType("success");
          setTimeout(() => { navigate("/dashboard"); window.location.reload(); }, 1500);
        }
      } else if (response.status === 409) {
        const errors = data.errors || ["This email or username is already registered."];
        setMessage(Array.isArray(errors) ? errors.join(" ") : errors);
        setMessageType("error");
      } else {
        const errors = data.errors || data.message || "Registration failed.";
        setMessage(Array.isArray(errors) ? errors.join(" ") : String(errors));
        setMessageType("error");
      }
    } catch (err) {
      console.error("[Register] Fetch failed:", err);
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
        <h1>Create Account</h1>
        <p>Register to start monitoring your mobile money wallets.</p>

        {message && (
          <div
            ref={messageRef}
            className={`message-box ${messageType}`}
            role="alert"
            aria-live="assertive"
          >
            <span className="message-icon">{messageType === "success" ? "✅" : "❌"}</span>
            {message}
          </div>
        )}

        <form onSubmit={handleRegister}>
          <div className="form-group">
            <label htmlFor="reg-fullname">Full Name</label>
            <input
              id="reg-fullname"
              type="text"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
              autoComplete="name"
              placeholder="e.g. Kwame Asante"
              aria-required="true"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-username">Username <span style={{ color: "var(--color-slate-400)", fontWeight: 400 }}>(optional)</span></label>
            <input
              id="reg-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder="e.g. kwame_asante"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-email">Email</label>
            <input
              id="reg-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              placeholder="e.g. kwame@example.com"
              aria-required="true"
            />
          </div>

          <div className="form-group">
            <label htmlFor="reg-phone">Phone Number</label>
            <input
              id="reg-phone"
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              required
              autoComplete="tel-national"
              placeholder="e.g. 0241234567"
              aria-required="true"
            />
          </div>

          <div className="form-group">
            <label htmlFor="register-password">Password</label>
            <PasswordInput
              id="register-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Upper + lower + digit + special"
              autoComplete="new-password"
            />
          </div>

          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "Registering..." : "Register"}
          </button>
        </form>

        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in here</Link>
        </p>
      </div>
    </div>
  );
}

export default Register;
