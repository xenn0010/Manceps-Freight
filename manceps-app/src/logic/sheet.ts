// Generic spreadsheet helpers: cell formatting, applying edits and CSV export.
import type { Column, Row, SheetTab } from "../data";

export interface SheetStep {
  tab: SheetTab;
  r: number;
  k: string;
  v: string | number | boolean;
}

/**
 * Rate per mile of a load row.
 *
 * Args:
 *   r: A load row.
 *
 * Returns:
 *   rate / miles, or null when either is missing.
 */
export function rpmOf(r: Row): number | null {
  const rate = Number(r.rate), miles = Number(r.miles);
  return r.rate && r.miles && miles ? rate / miles : null;
}

/**
 * Format one cell for display.
 *
 * Args:
 *   r: The row.
 *   k: The column key.
 *
 * Returns:
 *   The display string; empty when the value is missing.
 */
export function fmtCell(r: Row, k: string): string {
  if (k === "rate") return r.rate === "" ? "" : "$" + Number(r.rate).toLocaleString("en-US");
  if (k === "rpm") {
    const v = rpmOf(r);
    return v ? "$" + v.toFixed(2) : "";
  }
  if (k === "miles") return r.miles === "" ? "" : String(r.miles);
  const v = r[k];
  return v == null ? "" : String(v);
}

/**
 * Apply one planned edit to a list of rows.
 *
 * Args:
 *   rows: The rows of the edited tab.
 *   st: The edit.
 *
 * Returns:
 *   A new row list with the edited cell replaced.
 */
export function applyStep(rows: Row[], st: SheetStep): Row[] {
  return rows.map((r, ix) => (ix === st.r ? { ...r, [st.k]: st.v } : r));
}

/**
 * Serialize rows to CSV with every cell quoted.
 *
 * Args:
 *   cols: Column definitions.
 *   rows: Rows to export.
 *
 * Returns:
 *   CSV text with a header line.
 */
export function toCsv(cols: Column[], rows: Row[]): string {
  const head = cols.map((c) => c[1]).join(",");
  const body = rows.map((r) => cols.map((c) => '"' + fmtCell(r, c[0]).replace(/"/g, '""') + '"').join(","));
  return [head, ...body].join("\n");
}
