// ============================================================
// timeUtils.js — Relative timestamp helpers
// ============================================================
// Shows "Today, 3:45 PM" / "Yesterday" / "3 days ago" while
// keeping the full date accessible via title attribute.
// ============================================================

/**
 * Format a date string as a human-friendly relative label.
 * Returns { label, full } where:
 *   - label: short relative string for display
 *   - full:  full date+time string for the title tooltip
 */
export function relativeTime(dateStr) {
  if (!dateStr) return { label: "—", full: "" };

  const date = new Date(dateStr);
  const now  = new Date();
  const full = date.toLocaleString();

  // Strip time for day-level comparison
  const startOfToday     = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfDate      = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const daysDiff         = Math.round((startOfToday - startOfDate) / 86_400_000);

  const timeStr = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

  if (daysDiff === 0) return { label: `Today, ${timeStr}`, full };
  if (daysDiff === 1) return { label: `Yesterday, ${timeStr}`, full };
  if (daysDiff < 7)   return { label: `${daysDiff} days ago`, full };

  // Older than a week — show short date
  const shortDate = date.toLocaleDateString([], { month: "short", day: "numeric" });
  return { label: shortDate, full };
}
