import React from "react";
import { BrowserRouter as Router, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { ThemeProvider } from "./context/ThemeContext";
import { SidebarProvider } from "./context/SidebarContext";
import Navbar from "./components/Navbar";
import Sidebar from "./components/Sidebar";
import ProtectedRoute from "./components/ProtectedRoute";
import Dashboard from "./pages/Dashboard";
import Wallets from "./pages/Wallets";
import CheckMessage from "./pages/CheckMessage";
import MessageHistory from "./pages/MessageHistory";
import MessageCheckDetail from "./pages/MessageCheckDetail";
import ReviewQueue from "./pages/ReviewQueue";
import ReviewDetail from "./pages/ReviewDetail";
import Register from "./pages/Register";
import Login from "./pages/Login";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import "./App.css";

// Auth routes use a full-page centered layout — no sidebar chrome beside a login form.
const AUTH_ROUTES = ["/login", "/register", "/forgot-password", "/reset-password"];

function AppShell() {
  const location = useLocation();
  const isAuthRoute = AUTH_ROUTES.includes(location.pathname);

  return (
    <div className="app-layout">
      {/* Skip-to-content: WCAG 2.4.1 — lets keyboard/AT users bypass repeated nav */}
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Navbar />
      <div className="main-content">
        {!isAuthRoute && <Sidebar />}
        <div className="page-content" id="main-content">
          <Routes>
            {/* Default → Dashboard */}
            <Route path="/" element={<Navigate to="/dashboard" replace />} />

            {/* Protected pages — require token */}
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/wallets" element={<ProtectedRoute><Wallets /></ProtectedRoute>} />
            <Route path="/check-message" element={<ProtectedRoute><CheckMessage /></ProtectedRoute>} />
            <Route path="/message-history" element={<ProtectedRoute><MessageHistory /></ProtectedRoute>} />
            <Route path="/message-history/:id" element={<ProtectedRoute><MessageCheckDetail /></ProtectedRoute>} />

            {/* Legacy routes — redirect to dashboard so old bookmarks still work */}
            <Route path="/transactions" element={<Navigate to="/dashboard" replace />} />
            <Route path="/predictions" element={<Navigate to="/dashboard" replace />} />

            {/* Admin pages — require login AND admin role.
                Backend also enforces @admin_required on every /api/reviews/* route,
                providing defense-in-depth. Non-admin users are redirected to /dashboard. */}
            <Route path="/review-queue" element={<ProtectedRoute requiredRole="admin"><ReviewQueue /></ProtectedRoute>} />
            <Route path="/review-queue/:id" element={<ProtectedRoute requiredRole="admin"><ReviewDetail /></ProtectedRoute>} />

            {/* Public pages */}
            <Route path="/register" element={<Register />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />

            {/* Catch-all → Dashboard */}
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        </div>
      </div>
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <Router>
        <SidebarProvider>
          <AppShell />
        </SidebarProvider>
      </Router>
    </ThemeProvider>
  );
}

export default App;

