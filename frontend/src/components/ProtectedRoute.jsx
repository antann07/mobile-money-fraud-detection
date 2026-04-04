import React from "react";
import { Navigate } from "react-router-dom";

// ============================================================
// ProtectedRoute — guards routes by token presence and optional role
//
// Usage:
//   Token-only guard (any logged-in user):
//     <ProtectedRoute><Dashboard /></ProtectedRoute>
//
//   Role guard (must be logged in AND have the right role):
//     <ProtectedRoute requiredRole="admin"><ReviewQueue /></ProtectedRoute>
//
//   Future roles (analyst, reviewer) work the same way — just pass the string.
//
// Fallback behavior:
//   No token → redirect to /login
//   Wrong role → redirect to /dashboard (not a 404, not a blank page)
// ============================================================

/**
 * Decode the role claim from a JWT without verifying the signature.
 * Verification is the backend's responsibility; this is only for
 * client-side UI gating.
 */
function getRoleFromToken(token) {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role || "customer";
  } catch {
    return "customer";
  }
}

function ProtectedRoute({ children, requiredRole }) {
  const token = localStorage.getItem("token");

  // Not logged in → send to login
  if (!token) {
    return <Navigate to="/login" replace />;
  }

  // Role guard — only applies when the route declares a requiredRole
  if (requiredRole) {
    const actualRole = getRoleFromToken(token);
    if (actualRole !== requiredRole) {
      // Redirect to dashboard instead of showing a blank page or 403 screen.
      // The backend will also reject any API calls with 403, providing defense-in-depth.
      return <Navigate to="/dashboard" replace />;
    }
  }

  return children;
}

export default ProtectedRoute;
