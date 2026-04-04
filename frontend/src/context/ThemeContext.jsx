import React, { createContext, useContext, useState, useEffect, useLayoutEffect, useRef } from "react";

const ThemeContext = createContext();

const STORAGE_KEY = "theme-preference";

// Every preference the app can store. Kept explicit so stale or
// misspelled localStorage values are rejected before they cause silent bugs.
const VALID_PREFS = new Set(["default", "dark", "system"]);

// ── Helpers ────────────────────────────────────────────────────────────────

/** Current OS/browser color-scheme. Only called when pref === "system". */
function getSystemTheme() {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/**
 * Maps the STORED preference to the APPLIED CSS class.
 *
 *  "default"  →  always "light"   (app built-in theme, ignores OS)
 *  "dark"     →  always "dark"    (ignores OS)
 *  "system"   →  reads OS right now; updates live via a matchMedia listener
 *  anything else → "light"  (stale/corrupt localStorage)
 *
 * Note: "default" and "system" produce the same VISUAL result when the OS is
 * in light mode, but they are not the same preference. "default" is pinned;
 * "system" will switch to dark automatically if the OS goes dark.
 */
function resolveTheme(pref) {
  if (pref === "dark")   return "dark";
  if (pref === "system") return getSystemTheme(); // reads OS, not a fixed value
  return "light"; // "default" or any unrecognised value → pinned light
}

/** Rejects unknown or stale values. Safe default is "default" (pinned light). */
function sanitized(raw) {
  return VALID_PREFS.has(raw) ? raw : "default";
}

/** Writes the applied theme to <html data-theme="…">. */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

// ── Provider ───────────────────────────────────────────────────────────────

export function ThemeProvider({ children }) {
  // Read localStorage exactly once for both state initializers.
  // Lazy initializers (arrow-function form) run only on mount — React ignores
  // them on subsequent renders, so there is no repeated I/O cost.
  const storedPref = sanitized(localStorage.getItem(STORAGE_KEY));

  /** What the user chose: "default" | "dark" | "system" */
  const [preference, setPreference] = useState(() => storedPref);

  /** What is actually applied to <html>: "light" | "dark" */
  const [resolved, setResolved] = useState(() => resolveTheme(storedPref));

  // Track whether this is the very first render so the preference-change
  // effect does not re-write localStorage with the value we just read from it.
  const isFirstRender = useRef(true);

  // ── 1. DOM write (before paint, no flicker) ──────────────────────────────
  // useLayoutEffect fires synchronously after React commits but BEFORE the
  // browser paints. This eliminates the flash-of-wrong-theme on page load
  // that useEffect (post-paint) would cause.
  useLayoutEffect(() => {
    applyTheme(resolved);
  }, [resolved]);

  // ── 2. Persist preference + recompute resolved ───────────────────────────
  // Skipped on the very first render: localStorage already has the correct
  // value and resolved is already correct — no need to write or re-compute.
  // On subsequent renders (user clicks a button), we persist the NEW choice
  // and update the resolved theme.
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    // Store the PREFERENCE ("default" / "dark" / "system"), never the
    // RESOLVED value ("light" / "dark"). This keeps the user's intent intact
    // even when system mode resolves differently on different OS settings.
    localStorage.setItem(STORAGE_KEY, preference);
    setResolved(resolveTheme(preference));
  }, [preference]);

  // ── 3. Live OS tracking (system mode only) ───────────────────────────────
  // Attaches a matchMedia listener only while preference === "system".
  // Cleanup runs the moment the user switches to any other preference,
  // so "default" and "dark" are never affected by OS theme changes.
  useEffect(() => {
    if (preference !== "system") return; // not in system mode — no listener needed

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = (e) => setResolved(e.matches ? "dark" : "light");

    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler); // cleanup on pref change
  }, [preference]);

  return (
    <ThemeContext.Provider value={{ preference, resolved, setTheme: setPreference }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}
