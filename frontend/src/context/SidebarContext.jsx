import React, { createContext, useContext, useState } from "react";

// ============================================================
// SidebarContext — manages sidebar expanded/collapsed state
// ============================================================
// collapsed  : desktop sidebar is icon-only (persisted to localStorage)
// mobileOpen : mobile sidebar drawer is open (resets on navigation)
// ============================================================

const SidebarContext = createContext();

const STORAGE_KEY = "sidebar-collapsed";

export function SidebarProvider({ children }) {
  // Restore desktop collapsed preference from previous session.
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem(STORAGE_KEY) === "true"
  );

  // Mobile drawer open/closed — not persisted, resets on reload/navigation.
  const [mobileOpen, setMobileOpen] = useState(false);

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(STORAGE_KEY, String(next));
      return next;
    });
  }

  function openMobile()  { setMobileOpen(true);  }
  function closeMobile() { setMobileOpen(false); }

  return (
    <SidebarContext.Provider value={{ collapsed, toggleCollapsed, mobileOpen, openMobile, closeMobile }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext);
}
