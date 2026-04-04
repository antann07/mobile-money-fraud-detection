import React from "react";

// ============================================================
// PageLayout — Shared wrapper for all protected pages
// ============================================================
// Provides a consistent page header (title + subtitle) and
// spacing around the page content.
//
// Usage:
//   <PageLayout title="Dashboard" subtitle="Live overview of your app.">
//     <p>Page content goes here</p>
//   </PageLayout>
// ============================================================

function PageLayout({ title, subtitle, children }) {
  return (
    <div className="page-wrapper">
      <div className="page-header">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>

      <div className="page-body">{children}</div>
    </div>
  );
}

export default PageLayout;
