import React, { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import ThemeToggle from './ThemeToggle';
import { useSidebar } from '../context/SidebarContext';

function getUserRole() {
  // Decode JWT to get the role claim (without verifying — that's the backend's job)
  const token = localStorage.getItem("token");
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    return payload.role || "customer";
  } catch {
    return "customer";
  }
}

function Sidebar() {
  const location = useLocation();
  const token = localStorage.getItem("token");
  const role = getUserRole();
  const { collapsed, toggleCollapsed, mobileOpen, closeMobile } = useSidebar();
  const sidebarRef = useRef(null);

  // Focus trap: when mobile drawer opens, keep Tab cycle inside it.
  // Pressing Escape also closes the drawer. WCAG 2.1.2 / ARIA APG modal pattern.
  useEffect(() => {
    if (!mobileOpen) return;

    const sidebar = sidebarRef.current;
    if (!sidebar) return;

    // Capture initial focus on the toggle (close) button
    const firstFocusable = sidebar.querySelector(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    firstFocusable?.focus();

    function handleKeyDown(e) {
      if (e.key === 'Escape') {
        closeMobile();
        return;
      }
      if (e.key !== 'Tab') return;

      const focusable = Array.from(
        sidebar.querySelectorAll(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [mobileOpen, closeMobile]);

  const baseItems = [
    { path: '/dashboard',       label: 'Dashboard',       icon: '📊' },
    { path: '/check-message',   label: 'Check Message',   icon: '🛡️' },
    { path: '/message-history', label: 'Message History', icon: '📨' },
    { path: '/wallets',         label: 'My Wallets',      icon: '👛' },
  ];

  const adminItems = [
    { path: '/review-queue', label: 'Review Queue', icon: '🔍' },
  ];

  // For "/message-history/5" we still want "/message-history" highlighted
  function isActive(itemPath) {
    return location.pathname === itemPath || location.pathname.startsWith(itemPath + "/");
  }

  // Close mobile drawer when a link is clicked
  function handleLinkClick() {
    closeMobile();
  }

  function renderLinks(items) {
    return items.map((item) => (
      <Link
        key={item.path}
        to={item.path}
        className={`sidebar-link ${isActive(item.path) ? 'active' : ''}`}
        data-tooltip={item.label}   // CSS tooltip source (collapsed mode)
        title={item.label}          // accessibility / browser fallback
        aria-label={item.label}
        onClick={handleLinkClick}
      >
        <span className="icon" aria-hidden="true">{item.icon}</span>
        <span className="label">{item.label}</span>
      </Link>
    ));
  }

  return (
    <>
      {/* Mobile backdrop — clicking it closes the drawer */}
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={closeMobile}
          aria-hidden="true"
        />
      )}

      <aside
        ref={sidebarRef}
        className={[
          'sidebar',
          collapsed  ? 'sidebar--collapsed'    : '',
          mobileOpen ? 'sidebar--mobile-open'  : '',
        ].filter(Boolean).join(' ')}
        aria-label="Site navigation"
        aria-modal={mobileOpen ? 'true' : undefined}
      >
        {/* Header — collapse toggle on desktop, close button implied by backdrop on mobile */}
        <div className="sidebar-header">
          {!collapsed && (
            <div className="sidebar-header-text">
              <span className="sidebar-menu-label">Menu</span>
              <span className="sidebar-portal-label">
                {role === "admin" ? "Admin Portal" : "Customer Portal"}
              </span>
            </div>
          )}
          <button
            className="sidebar-toggle-btn"
            onClick={mobileOpen ? closeMobile : toggleCollapsed}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? '›' : '‹'}
          </button>
        </div>

        <nav className="sidebar-nav" role="navigation" aria-label="Main navigation">
          {renderLinks(baseItems)}

          {token && role === 'admin' && (
            <>
              <div className="sidebar-divider">
                {!collapsed && <span>Admin</span>}
              </div>
              {renderLinks(adminItems)}
            </>
          )}

          {!token && renderLinks([
            { path: '/login',    label: 'Sign In',  icon: '🔑' },
            { path: '/register', label: 'Register', icon: '📝' },
          ])}
        </nav>

        <div className="sidebar-footer">
          <ThemeToggle />
          {!collapsed && (
            <span className="sidebar-copyright">© 2026 Mobile Money Protection System</span>
          )}
        </div>
      </aside>
    </>
  );
}

export default Sidebar;
