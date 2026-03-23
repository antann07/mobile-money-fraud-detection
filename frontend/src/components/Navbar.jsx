import React from 'react';

function Navbar() {
  return (
    <header className="navbar">
      <div className="navbar-content">
        <div className="navbar-logo">🛡️</div>
        <div>
          <h1 className="navbar-title">Mobile Money Fraud Detection & Protection System</h1>
          <p className="navbar-subtitle">AI-Assisted Mobile Money Fraud Protection</p>
        </div>
        <div className="navbar-right">
          <span className="navbar-status">
            <span className="status-dot"></span>
            System Active
          </span>
          <div className="navbar-user">
            <div className="navbar-avatar">AD</div>
          </div>
        </div>
      </div>
    </header>
  );
}

export default Navbar;