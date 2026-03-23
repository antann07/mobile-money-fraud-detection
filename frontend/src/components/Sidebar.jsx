import React from 'react';
import { Link, useLocation } from 'react-router-dom';

function Sidebar() {
  const location = useLocation();

  const menuItems = [
    { path: '/dashboard', label: 'Protection Dashboard', icon: '📊' },
    { path: '/transactions', label: 'Money Activity', icon: '💳' },
    { path: '/fraud-alerts', label: 'Safety Alerts', icon: '⚠️' },
    { path: '/fraud-cases', label: 'Investigation Cases', icon: '🧩' },
    { path: '/create-transaction', label: 'Record Transaction', icon: '➕' }
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <h3>Menu</h3>
        <p className="sidebar-subtitle">Customer Protection Portal</p>
      </div>
      <nav className="sidebar-nav">
        {menuItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`sidebar-link ${location.pathname === item.path ? 'active' : ''}`}
          >
            <span className="icon" aria-hidden="true">{item.icon}</span>
            <span className="label">{item.label}</span>
          </Link>
        ))}
      </nav>
      <div className="sidebar-footer">
        © 2026 Mobile Money Protection System
      </div>
    </aside>
  );
}

export default Sidebar;