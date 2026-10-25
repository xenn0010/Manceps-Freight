// User actions shared by live and demo surfaces: toasts, selection, chat focus and keyboard shortcuts.
import { agentOf } from "./agents";
import { nameParts } from "./logic/derive";
import { getMap } from "./map/registry";
import { getState, setState } from "./store";

export const TOAST_MS = 4200;
export const UI_TICK_MS = 1000;
const FOCUS_DELAY_MS = 50;

let toastT: number | undefined;
let focusChat: (() => void) | null = null;

/**
 * Register how to focus the chat box when chat opens.
 *
 * Args:
 *   fn: Focus callback, or null on unmount.
 */
export function setChatFocus(fn: (() => void) | null): void {
  focusChat = fn;
}

/**
 * Show a toast for a few seconds.
 *
 * Args:
 *   text: Toast text.
 *   demo: True for scripted demo activity; the toast then shows a Demo tag.
 */
export function showToast(text: string, demo = false): void {
  window.clearTimeout(toastT);
  setState({ toast: { text, demo } });
  toastT = window.setTimeout(() => setState({ toast: null }), TOAST_MS);
}

/** The agent's display name from the firm's current selection. */
export function agentName(): string {
  return agentOf(getState().agent).name;
}

/**
 * First name of a truck's first driver, for call labels.
 *
 * Args:
 *   truckId: Backend truck id.
 *
 * Returns:
 *   The first name, or "Driver" when the truck has no named driver.
 */
export function driverFirst(truckId: string): string {
  const d = getState().trucks.find((t) => t.id === truckId)?.drivers[0];
  return d?.name ? nameParts(d.name).first : "Driver";
}

/**
 * Select a truck (or none), close the account panel and move the map.
 *
 * Args:
 *   id: Truck to select, or null.
 */
export function pick(id: string | null): void {
  setState({ sel: id, me: false, tab: "load" });
  getMap()?.select(id);
}

/** Open the chat and focus its text box. */
export function openChat(): void {
  setState({ chat: true });
  window.setTimeout(() => focusChat?.(), FOCUS_DELAY_MS);
}

function onKeyDown(e: KeyboardEvent): void {
  const tag = ((e.target as HTMLElement | null)?.tagName ?? "").toLowerCase();
  const s = getState();
  if (e.key === "Escape") {
    if (s.panel) setState({ panel: null });
    else if (s.chat) setState({ chat: false });
    else if (s.sel) pick(null);
    return;
  }
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  if (e.key === "/") { e.preventDefault(); openChat(); }
}

/**
 * Start keyboard shortcuts and the UI clock that drives call timers and edit flashes.
 *
 * Returns:
 *   A cleanup function that stops both.
 */
export function startUiRuntime(): () => void {
  window.addEventListener("keydown", onKeyDown);
  const pt = window.setInterval(() => {
    const s = getState();
    if (s.sel || s.call || s.view === "sheet") setState((x) => ({ tick: x.tick + 1 }));
  }, UI_TICK_MS);
  return () => {
    window.removeEventListener("keydown", onKeyDown);
    window.clearInterval(pt);
    window.clearTimeout(toastT);
  };
}
