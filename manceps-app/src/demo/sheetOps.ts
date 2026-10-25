// Demo: the agent's scripted sheet operations (find backhauls, negotiate, flag, book, rate cons, text drivers).
import type { Row } from "../data";
import { rpmOf, type SheetStep } from "../logic/sheet";
import { BACKHAUL, BACKHAUL_101_ID, type Perm } from "./data";

/** Minimum $/mile the agent treats as a good offer. */
export const RPM_FLOOR = 3.6;
/** Negotiation bump applied to offers. */
export const NEGOTIATE_FACTOR = 1.07;
/** Rates are rounded to this many dollars after negotiation. */
const RATE_ROUNDING = 10;

export type SheetOpKind = "backhaul" | "negotiate" | "flag" | "book" | "ratecons" | "text";

export type SheetPlan =
  | { error: string }
  | { label: string; steps: SheetStep[]; switchToDrivers: boolean; booksBackhaul101: boolean };

export interface SheetInput {
  loads: Row[];
  drivers: Row[];
  rowsSel: number[];
  perm: Perm;
  /** The agent's display name, for messages. */
  agentName: string;
}

const step = (r: number, k: string, v: SheetStep["v"]): SheetStep => ({ tab: "loads", r, k, v });

/** Selected rows that pass `ok`, or every passing row when nothing is selected. */
function pickRows(input: SheetInput, ok: (r: Row) => boolean): number[] {
  const sel = input.rowsSel.filter((i) => { const r = input.loads[i]; return r !== undefined && ok(r); });
  return sel.length ? sel : input.loads.map((_, i) => i).filter((i) => ok(input.loads[i] as Row));
}

function planBackhaul(L: Row[]): SheetStep[] {
  const st: SheetStep[] = [];
  L.forEach((r, i) => {
    const b = BACKHAUL[i];
    if (r.status !== "Open" || !b) return;
    for (const k of ["id", "lane", "delivery", "miles", "rate", "broker"]) st.push(step(i, k, b[k] as SheetStep["v"]));
    st.push(step(i, "status", "Proposed"), step(i, "notes", b.notes as string));
  });
  return st;
}

function planNegotiate(input: SheetInput): SheetStep[] {
  const L = input.loads, st: SheetStep[] = [];
  pickRows(input, (r) => ["Offer", "Proposed"].includes(String(r.status)) && Boolean(r.rate)).forEach((i) => {
    const row = L[i] as Row, rate = Number(row.rate);
    const nr = Math.round((rate * NEGOTIATE_FACTOR) / RATE_ROUNDING) * RATE_ROUNDING;
    st.push(step(i, "notes", "Calling " + String(row.broker) + "…"), step(i, "rate", nr), step(i, "notes", "Countered +$" + (nr - rate) + " · accepted"));
  });
  return st;
}

function planFlag(L: Row[]): SheetStep[] {
  const st: SheetStep[] = [];
  L.forEach((r, i) => {
    const v = rpmOf(r);
    if (v && v < RPM_FLOOR && r.status === "Offer") st.push(step(i, "flag", true), step(i, "notes", "Under your $3.60/mi floor · I'd pass"));
  });
  return st;
}

function planRateCons(L: Row[]): SheetStep[] {
  const st: SheetStep[] = [];
  L.forEach((r, i) => {
    if (r.status === "Booked") st.push(step(i, "status", "Rate con sent"), step(i, "notes", "Signed & sent to " + String(r.broker)));
  });
  return st;
}

function planText(drivers: Row[]): SheetStep[] {
  return drivers.flatMap((d, i): SheetStep[] => [
    { tab: "drivers", r: i, k: "notes", v: "Texted tomorrow's plan · " + (d.duty === "Off duty" || d.duty === "Inactive" ? "will read at 07:00" : "read ✓") },
    { tab: "drivers", r: i, k: "checkin", v: "Just now · WhatsApp" },
  ]);
}

/**
 * Plan the cell edits for one of the agent's sheet operations. Booking and rate cons only run from the owner's own
 * tap on the chip or command, which is the one-tap approval those actions always need.
 *
 * Args:
 *   kind: Which operation to run.
 *   input: Current loads, drivers, row selection, permissions and agent name.
 *
 * Returns:
 *   The label and ordered cell edits, or an error when a permission blocks it.
 */
export function planSheetOp(kind: SheetOpKind, input: SheetInput): SheetPlan {
  const base = { switchToDrivers: false, booksBackhaul101: false };
  switch (kind) {
    case "backhaul":
      return { ...base, label: "Found backhauls for open trucks", steps: planBackhaul(input.loads) };
    case "negotiate":
      if (input.perm.negotiate === "off") return { error: "Negotiating is off for " + input.agentName + " · change it in Permissions" };
      return { ...base, label: "Negotiated offers +7%", steps: planNegotiate(input) };
    case "book": {
      const ids = pickRows(input, (r) => ["Offer", "Proposed", "Needs your yes"].includes(String(r.status)) && (rpmOf(r) ?? 0) >= RPM_FLOOR);
      const steps = ids.flatMap((i) => [step(i, "status", "Booked"), step(i, "notes", "Booked · rate con requested")]);
      const hit = ids.some((i) => input.loads[i]?.id === BACKHAUL_101_ID);
      return { ...base, label: "Booked " + ids.length + (ids.length === 1 ? " load" : " loads"), steps, booksBackhaul101: hit };
    }
    case "flag":
      return { ...base, label: "Flagged loads under $3.60/mi", steps: planFlag(input.loads) };
    case "ratecons":
      return { ...base, label: "Sent rate confirmations", steps: planRateCons(input.loads) };
    case "text":
      return { ...base, label: "Texted every driver tomorrow's plan", steps: planText(input.drivers), switchToDrivers: true };
  }
}

/**
 * Map a typed sheet command to an operation by keyword.
 *
 * Args:
 *   q: The user's text.
 *
 * Returns:
 *   The matching operation, or null when nothing matches.
 */
export function classifyCommand(q: string): SheetOpKind | null {
  const s = q.toLowerCase();
  if (/backhaul|open|empty|find/.test(s)) return "backhaul";
  if (/negotiat|counter|more money|raise/.test(s)) return "negotiate";
  if (/flag|low|floor|cheap/.test(s)) return "flag";
  if (/rate con|confirm|sign|send/.test(s)) return "ratecons";
  if (/text|driver|message|whatsapp/.test(s)) return "text";
  if (/book|accept/.test(s)) return "book";
  return null;
}
