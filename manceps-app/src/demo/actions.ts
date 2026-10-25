// Demo: scripted agent activity (dispatch feed, scripted calls, canned chat, booking, sheet operations).
// Every toast these raise carries a Demo tag. Replace a function here with an API call to make it live.
import { agentName, driverFirst, showToast } from "../actions";
import { applyStep, type SheetStep } from "../logic/sheet";
import { getMap } from "../map/registry";
import { getState, setState, type CallMode } from "../store";
import { ANSWERS, BACKHAUL_101_ID, DISPATCHES, FALLBACK_ANSWER, type Perm } from "./data";
import { callScript, fillNames } from "./scripts";
import { planSheetOp, type SheetOpKind } from "./sheetOps";

export const CALL_LINE_MS = 2800;
export const SHEET_STEP_MS = 260;
export const ANSWER_DELAY_MS = 650;
export const DISPATCH_EVERY_MS = 9000;
export const FIRST_DISPATCH_MS = 3500;
export const BEN_CALL_MS = 12000;
/** Lines in the scripted demo call with Ben about the 102 window. */
const BEN_CALL_LINES = 5;

let callT: number | undefined;
let opT: number | undefined;
let benT: number | undefined;

/** Show the next scripted demo dispatch event as a toast and a map pulse. */
export function dispatchTick(): void {
  const s = getState();
  const ev = DISPATCHES[s.di % DISPATCHES.length];
  if (!ev) return;
  getMap()?.pulse(ev[1]);
  showToast(fillNames(ev[0], agentName(), ""), true);
  setState((x) => ({ di: x.di + 1 }));
}

/** End the current call, if any, and clear its bubble. */
export function endCall(): void {
  window.clearInterval(callT);
  const c = getState().call;
  if (!c) return;
  getMap()?.say(c.id, null);
  setState({ call: null });
}

/**
 * The scripted lines for a truck's agent call.
 *
 * Args:
 *   truckId: Backend truck id.
 *
 * Returns:
 *   Speaker label and text per line.
 */
export function scriptFor(truckId: string): [string, string][] {
  const i = getState().trucks.findIndex((t) => t.id === truckId);
  return callScript(i, agentName(), driverFirst(truckId));
}

function showAgentLine(id: string): void {
  const c = getState().call;
  const line = scriptFor(id)[c?.step ?? 0];
  if (!c || c.mode !== "agent" || !line) return;
  const [w, x] = line;
  getMap()?.say(id, { mode: "agent", who: w === agentName() ? w + " → " + driverFirst(id) : w, text: x });
}

/**
 * Start a scripted demo call with a truck's driver.
 *
 * Args:
 *   id: Truck whose driver is called.
 *   mode: "you" for the user, "agent" for the agent reading the script.
 */
export function startCall(id: string, mode: CallMode): void {
  endCall();
  setState({ call: { id, mode, t0: Date.now(), step: 0 }, mute: false });
  if (mode === "you") {
    getMap()?.say(id, { mode: "you", who: "Calling " + driverFirst(id) + "…", text: "" });
    return;
  }
  const lines = scriptFor(id);
  showAgentLine(id);
  callT = window.setInterval(() => {
    const c = getState().call;
    if (!c) return;
    if (c.step >= lines.length - 1) { endCall(); showToast(agentName() + " wrapped up with " + driverFirst(id), true); return; }
    setState({ call: { ...c, step: c.step + 1 } });
    showAgentLine(id);
  }, CALL_LINE_MS);
}

/**
 * Send a question to the agent and post the canned answer.
 *
 * Args:
 *   q: The question.
 */
export function ask(q: string): void {
  if (!q.trim()) return;
  setState((s) => ({ chat: true, text: "", msgs: [...s.msgs, { me: true, text: q }] }));
  const a = ANSWERS[q] ?? FALLBACK_ANSWER;
  window.setTimeout(() => setState((s) => ({ msgs: [...s.msgs, { me: false, text: a }] })), ANSWER_DELAY_MS);
}

/**
 * Book the 101 backhaul; only ever called from the owner's own tap.
 *
 * Args:
 *   fromSheet: Keep the sheet's own note instead of "Booked from the map".
 */
export function book(fromSheet = false): void {
  setState((s) => ({
    booked: true,
    loads: s.loads.map((r) => (r.id === BACKHAUL_101_ID ? { ...r, status: "Booked", notes: fromSheet ? r.notes ?? "" : "Booked from the map" } : r)),
  }));
  getMap()?.book();
  showToast("Booked · Commerce → SF · $2,240", true);
}

/**
 * Change the agent's permissions. Booking and signing stay at "ask" by type; nothing books on its own.
 *
 * Args:
 *   patch: Fields to change.
 */
export function setPerm(patch: Partial<Perm>): void {
  setState((s) => ({ perm: { ...s.perm, ...patch, book: "ask", sign: "ask" } }));
}

/** Mark the 102 heads-up as handled. */
export function ackLate102(): void {
  setState({ r102: true });
  showToast("Stockton confirmed the 15:30–16:30 window", true);
}

function applySheetStep(st: SheetStep): void {
  setState((s) => ({
    ...(st.tab === "loads" ? { loads: applyStep(s.loads, st) } : { drivers: applyStep(s.drivers, st) }),
    agentCell: { tab: st.tab, r: st.r, k: st.k },
    flash: { ...s.flash, [st.tab + st.r + st.k]: Date.now() },
    cell: { r: st.r, k: st.k },
  }));
}

/**
 * Play a list of cell edits one at a time, as if the agent were typing them.
 *
 * Args:
 *   label: What the agent is doing, shown in the status bar.
 *   steps: Ordered cell edits.
 *   done: Called after the last edit.
 */
export function runSheet(label: string, steps: SheetStep[], done?: () => void): void {
  if (getState().busy) return;
  if (!steps.length) { showToast("Nothing to do there", true); return; }
  window.clearInterval(opT);
  let i = 0;
  setState({ busy: label });
  opT = window.setInterval(() => {
    const st = steps[i++];
    if (st) { applySheetStep(st); return; }
    window.clearInterval(opT);
    setState((s) => ({ agentCell: null, busy: null, done: [...s.done, label] }));
    done?.();
    showToast(agentName() + " · " + label + " ✓", true);
  }, SHEET_STEP_MS);
}

/**
 * Run one of the agent's sheet operations.
 *
 * Args:
 *   kind: Which operation.
 */
export function sheetOp(kind: SheetOpKind): void {
  const s = getState();
  const plan = planSheetOp(kind, { loads: s.loads, drivers: s.drivers, rowsSel: s.rowsSel, perm: s.perm, agentName: agentName() });
  if ("error" in plan) { showToast(plan.error, true); return; }
  if (plan.switchToDrivers) setState({ sheetTab: "drivers", rowsSel: [] });
  const after = plan.booksBackhaul101 ? (): void => { if (!getState().booked) book(true); } : undefined;
  runSheet(plan.label, plan.steps, after);
}

function benCall(): void {
  const s = getState();
  if (s.r102) return;
  if (s.perm.drivers === "off") return;
  if (s.perm.drivers === "ask") { showToast(agentName() + " wants to call Ben about 102 · see the Heads up card", true); return; }
  showToast(agentName() + " is calling Ben about the new window", true);
  benT = window.setTimeout(() => { setState({ r102: true }); showToast("Ben's up to date · 102 on time ✓", true); }, CALL_LINE_MS * BEN_CALL_LINES);
}

/**
 * Start the demo's background timers.
 *
 * Returns:
 *   A cleanup function that stops them.
 */
export function startDemoRuntime(): () => void {
  const dt = window.setInterval(dispatchTick, DISPATCH_EVERY_MS);
  const first = window.setTimeout(dispatchTick, FIRST_DISPATCH_MS);
  const rt = window.setTimeout(benCall, BEN_CALL_MS);
  return () => {
    [dt, callT, opT].forEach((t) => window.clearInterval(t));
    [first, rt, benT].forEach((t) => window.clearTimeout(t));
  };
}
