import { agentOf } from "../agents";
import { DCOLS, LETTERS, STATUS, type Column, type Row } from "../data";
import { LCOLS, type SheetOpKind } from "../demo";
import type { State } from "../store";
import { fmtCell } from "./sheet";

/** How long an edited cell stays highlighted. */
export const FLASH_MS = 1600;

export interface CellView {
  v: string;
  justify: string;
  bg: string;
  ink: string;
  pbg: string;
  pp: string;
  ring: string;
  z: number;
  agent: boolean;
}

/** Labels that mark an operation as done once it has run. */
const DONE_LABELS: Partial<Record<SheetOpKind, string>> = {
  backhaul: "Found backhauls for open trucks",
  flag: "Flagged loads under $3.60/mi",
  ratecons: "Sent rate confirmations",
  text: "Texted every driver tomorrow's plan",
};

/**
 * Columns and rows for the active sheet tab.
 *
 * Args:
 *   s: Current state.
 *
 * Returns:
 *   The tab's columns and rows.
 */
export function activeSheet(s: Pick<State, "sheetTab" | "loads" | "drivers" | "agent">): { cols: Column[]; rows: Row[]; isLoads: boolean } {
  const isLoads = s.sheetTab === "loads", notes = agentOf(s.agent).name + "'s notes";
  const cols = (isLoads ? LCOLS : DCOLS).map((c): Column => (c[0] === "notes" ? [c[0], notes, c[2], c[3]] : c));
  return { cols, rows: isLoads ? s.loads : s.drivers, isLoads };
}

/** CSS justify-content for a column alignment. */
export function justifyFor(al: Column[3]): string {
  return al === "r" ? "flex-end" : al === "c" ? "center" : "flex-start";
}

/**
 * Title and subtitle above the sheet.
 *
 * Args:
 *   isLoads: Whether the loads tab is active.
 *   rows: Rows of the active tab.
 *
 * Returns:
 *   Title and row-count summary.
 */
export function sheetHeading(isLoads: boolean, rows: Row[]): { title: string; sub: string } {
  if (!isLoads) return { title: "Drivers", sub: rows.length + (rows.length === 1 ? " driver · " : " drivers · ") + rows.filter((r) => r.duty === "Active").length + " active" };
  const booked = rows.filter((r) => r.status === "Booked" || r.status === "Rate con sent").length;
  const open = rows.filter((r) => r.status === "Open").length;
  return { title: "Loads · week of Oct 26", sub: rows.length + " rows · " + booked + " booked · " + open + " open" };
}

/**
 * Formula bar contents for the selected cell.
 *
 * Args:
 *   s: Current state.
 *
 * Returns:
 *   Cell reference like "H5" and its value or formula.
 */
export function formulaBar(s: Pick<State, "sheetTab" | "loads" | "drivers" | "cell" | "agent">): { ref: string; val: string } {
  const { cols, rows } = activeSheet(s);
  const ci = cols.findIndex((c) => c[0] === s.cell.k);
  const row = rows[s.cell.r];
  if (ci < 0) return { ref: "", val: "" };
  const ref = (LETTERS[ci] ?? "") + (s.cell.r + 2);
  if (!row) return { ref, val: "" };
  const val = s.cell.k === "rpm" && row.rate ? "=H" + (s.cell.r + 2) + "/G" + (s.cell.r + 2) : fmtCell(row, s.cell.k);
  return { ref, val };
}

/**
 * Quick-action chips for the active tab.
 *
 * Args:
 *   s: Current state.
 *
 * Returns:
 *   Operation, label and done flag per chip.
 */
export function sheetChips(s: Pick<State, "sheetTab" | "rowsSel" | "done">): { k: SheetOpKind; label: string; done: boolean }[] {
  const n = s.rowsSel.length;
  const defs: [SheetOpKind, string][] = s.sheetTab === "loads"
    ? [["backhaul", "Find backhauls for open trucks"], ["negotiate", n ? "Negotiate " + n + " selected +7%" : "Negotiate offers +7%"], ["flag", "Flag anything under $3.60/mi"], ["book", n ? "Book " + n + " selected" : "Book good offers"], ["ratecons", "Send rate cons"], ["text", "Text drivers tomorrow's plan"]]
    : [["text", "Text drivers tomorrow's plan"]];
  return defs.map(([k, label]) => {
    const key = DONE_LABELS[k];
    const done = Boolean(key && s.done.includes(key));
    return { k, label: done ? label + " ✓" : label, done };
  });
}

/**
 * Status line in the sheet footer.
 *
 * Args:
 *   busy: What the agent is doing, if anything.
 *   nSel: Number of selected rows.
 *   agent: The agent's display name.
 *   isLoads: Whether the loads tab is active.
 *
 * Returns:
 *   Text, text color and dot color.
 */
export function sheetStatus(busy: string | null, nSel: number, agent: string, isLoads = true): { text: string; ink: string; dot: string } {
  const idle = isLoads ? "Click a row number to select it, then ask " + agent : "Double-click a cell to edit it · changes save to your account";
  const text = busy ? agent + " · " + busy + "…" : nSel ? nSel + " row" + (nSel > 1 ? "s" : "") + " selected · click a row number to select" : idle;
  return { text, ink: busy ? "#1B5E94" : "#64748A", dot: busy ? "#2272AD" : "#1F9A5A" };
}

/**
 * Display state of one cell: value, colors, pill, selection ring and agent cursor.
 *
 * Args:
 *   s: Current state.
 *   r: The row.
 *   ri: Row index.
 *   col: Column definition.
 *   now: Current time in ms, for edit flashes.
 *
 * Returns:
 *   Everything the cell needs to render.
 */
export function cellView(s: Pick<State, "sheetTab" | "cell" | "agentCell" | "flash">, r: Row, ri: number, col: Column, now: number): CellView {
  const [k, , , al] = col;
  const v = fmtCell(r, k);
  const isSel = s.cell.r === ri && s.cell.k === k;
  const ac = s.agentCell && s.agentCell.tab === s.sheetTab ? s.agentCell : null;
  const isAg = Boolean(ac && ac.r === ri && ac.k === k);
  const since = (key: string): number => now - (s.flash[s.sheetTab + ri + key] ?? 0);
  const fl = since(k) < FLASH_MS || (k === "rpm" && since("rate") < FLASH_MS);
  const st = k === "status" || k === "duty" ? STATUS[v] : undefined;
  const low = k === "rpm" && r.flag === true;
  return {
    v: v || " ", justify: justifyFor(al),
    bg: fl ? "rgba(34,114,173,.16)" : low ? "rgba(227,154,45,.16)" : "transparent",
    ink: st ? st[1] : low ? "#8A5A12" : k === "notes" ? "#1B5E94" : v === "" ? "#8C9AAD" : "#010D1D",
    pbg: st ? st[0] : "transparent", pp: st ? "3px 8px" : "0",
    ring: isAg ? "inset 0 0 0 2px #2272AD" : isSel ? "inset 0 0 0 2px #010D1D" : "none", z: isAg ? 2 : isSel ? 1 : 0, agent: isAg,
  };
}
