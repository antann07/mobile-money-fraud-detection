import React from "react";
import { useNavigate } from "react-router-dom";
import { useSidebar } from "../context/SidebarContext";

function getUserRole() {
  const token = localStorage.getItem("token");
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role || "customer";
  } catch {
    return "customer";
  }
}

/**
 * Return the best available display label for the logged-in user.
 * Fallback chain: full_name → username → email → role
 */
function getUserDisplayName() {
  try {
    const raw = localStorage.getItem("user");
    if (!raw) return null;
    const user = JSON.parse(raw);
    return (
      user.full_name?.trim() ||
      user.username?.trim() ||
      user.email?.trim() ||
      null
    );
  } catch {
    return null;
  }
}

function Navbar() {
  const navigate = useNavigate();
  const token = localStorage.getItem("token");
  const role = getUserRole();
  const displayName = getUserDisplayName();
  const { openMobile, collapsed } = useSidebar();

  function handleLogout() {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    navigate("/login");
    window.location.reload();
  }

  return (
    <header className="navbar">
      <div className="navbar-content">
        {/* Hamburger — mobile only, shows sidebar drawer */}
        <button
          className="navbar-hamburger"
          onClick={openMobile}
          aria-label="Open navigation"
        >
          <span /><span /><span />
        </button>

        {/* Brand — min-width tracks sidebar width so the T-intersection holds.
            At collapsed state uses .navbar--sidebar-collapsed to shrink to 64px rail. */}
        <div className={`navbar-brand${collapsed ? " navbar-brand--collapsed" : ""}`}>
          <span className="navbar-logo">🛡️</span>
          <div>
            <h1 className="navbar-title">Fraud Detection</h1>
            <span className="navbar-subtitle">Mobile Money Protection</span>
          </div>
        </div>

        {/* Right side — status, user identity, role badge, logout */}
        <div className="navbar-right">
          <span className="navbar-status">
            <span className="status-dot"></span>
            System Active
          </span>
          {token && displayName && (
            <span className="navbar-user-identity" title={role || "customer"}>
              {displayName}
            </span>
          )}
          {token && role === "admin" && (
            <span className="navbar-role-badge">Admin</span>
          )}
          {token && (
            <button onClick={handleLogout} className="btn-logout">
              Logout
            </button>
          )}
        </div>
      </div>
    </header>
  );
}

export default Navbar;