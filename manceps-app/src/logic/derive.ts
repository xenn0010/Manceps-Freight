// Small formatting helpers shared by live and demo surfaces.

/**
 * Text and dot color for the header's "things for you" button.
 *
 * Args:
 *   count: Number of open needs.
 *
 * Returns:
 *   Dot color, dot mark and label.
 */
export function needSummary(count: number): { dot: string; mark: string; text: string } {
  if (!count) return { dot: "#1F9A5A", mark: "✓", text: "All clear" };
  return { dot: "#2272AD", mark: String(count), text: count === 1 ? "1 thing for you" : count + " things for you" };
}

/**
 * Format a minute count as "N min" or "H h M m".
 *
 * Args:
 *   m: Minutes.
 *
 * Returns:
 *   Human-readable duration.
 */
export function fmtMinutes(m: number): string {
  return m >= 60 ? Math.floor(m / 60) + " h " + (m % 60) + " m" : m + " min";
}

/**
 * Format elapsed seconds as m:ss.
 *
 * Args:
 *   sec: Elapsed seconds, non-negative.
 *
 * Returns:
 *   Clock text like "1:05".
 */
export function fmtClock(sec: number): string {
  return Math.floor(sec / 60) + ":" + String(sec % 60).padStart(2, "0");
}

/** Initials and first name for a driver's full name. */
export function nameParts(full: string): { first: string; initials: string } {
  const parts = full.split(" ");
  return { first: parts[0] ?? full, initials: parts.map((w) => w[0] ?? "").join("") };
}
