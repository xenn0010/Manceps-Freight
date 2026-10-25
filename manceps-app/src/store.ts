import { useSyncExternalStore } from "react";
import type { AgentSelection } from "./agents";
import type { Carrier } from "./api/types";
import type { Row, SheetTab } from "./data";
import { LOADS0, PRESETS, type Perm } from "./demo/data";
import { loadAgentSelection } from "./demo/agentSettings";
import type { ProfileView, TruckView } from "./live/mappers";

export type CallMode = "you" | "agent";
export type TruckTab = "load" | "driver" | "route" | "truck";
export type MeTab = "dash" | "profile" | "settings";
export type NotifKey = "push" | "wa" | "digest";
export type View = "map" | "sheet";
/** booting: trying the refresh cookie; provisioning: firm being set up; ready: firm-scoped token in hand. */
export type Session = "booting" | "signedOut" | "provisioning" | "ready";
export type FleetStatus = "idle" | "loading" | "ready" | "error";
export type Panel = "addTruck" | "import" | null;

export interface CallState {
  id: string;
  mode: CallMode;
  t0: number;
  step: number;
}

export interface Msg {
  me: boolean;
  text: string;
}

export interface CellRef {
  r: number;
  k: string;
}

export interface AgentCell extends CellRef {
  tab: SheetTab;
}

export interface Toast {
  text: string;
  /** True for toasts from scripted demo activity; they show a Demo tag. */
  demo: boolean;
}

/** An open drivers sheet cell editor. */
export interface CellEditor extends CellRef {
  v: string;
  saving: boolean;
}

export interface State {
  session: Session;
  /** Why the user is on the sign-in screen, e.g. the session expired. */
  sessionNote: string | null;
  profile: ProfileView | null;
  fleetStatus: FleetStatus;
  fleetError: string | null;
  trucks: TruckView[];
  carriers: Carrier[];
  panel: Panel;
  editor: CellEditor | null;
  agent: AgentSelection;
  sel: string | null;
  chat: boolean;
  text: string;
  msgs: Msg[];
  booked: boolean;
  r102: boolean;
  later: string[];
  toast: Toast | null;
  di: number;
  call: CallState | null;
  tick: number;
  mute: boolean;
  tab: TruckTab;
  me: boolean;
  view: View;
  sheetTab: SheetTab;
  loads: Row[];
  drivers: Row[];
  cell: CellRef;
  rowsSel: number[];
  agentCell: AgentCell | null;
  flash: Record<string, number>;
  busy: string | null;
  cmd: string;
  done: string[];
  meTab: MeTab;
  notif: Record<NotifKey, boolean>;
  permOpen: boolean;
  perm: Perm;
  quiet: boolean;
}

/**
 * Build the initial screen state.
 *
 * Returns:
 *   A fresh State: booting session, no live data yet, demo loads and the Balanced preset.
 */
export function initialState(): State {
  return {
    session: "booting", sessionNote: null, profile: null, fleetStatus: "idle", fleetError: null, trucks: [], carriers: [],
    panel: null, editor: null, agent: loadAgentSelection(),
    sel: null, chat: false, text: "", msgs: [], booked: false, r102: false, later: [], toast: null, di: 0,
    call: null, tick: 0, mute: false, tab: "load", me: false, view: "map", sheetTab: "loads",
    loads: LOADS0.map((r) => ({ ...r })), drivers: [],
    cell: { r: 3, k: "rate" }, rowsSel: [], agentCell: null, flash: {}, busy: null, cmd: "", done: [],
    meTab: "dash", notif: { push: true, wa: true, digest: false }, permOpen: false,
    perm: { ...PRESETS.balanced[2] }, quiet: true,
  };
}

type Patch = Partial<State> | ((s: State) => Partial<State>);

let state: State = initialState();
const listeners = new Set<() => void>();

/**
 * Return the current state snapshot.
 *
 * Returns:
 *   The live State object; treat it as read-only.
 */
export function getState(): State {
  return state;
}

/**
 * Merge a patch into the state and notify subscribers.
 *
 * Args:
 *   patch: A partial state, or a function of the current state returning one.
 */
export function setState(patch: Patch): void {
  const next = typeof patch === "function" ? patch(state) : patch;
  state = { ...state, ...next };
  listeners.forEach((l) => l());
}

/**
 * Replace the whole state; used by tests and sign-out to start from a clean slate.
 *
 * Args:
 *   next: The state to install.
 */
export function resetState(next: State = initialState()): void {
  state = next;
  listeners.forEach((l) => l());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Subscribe a component to the store.
 *
 * Returns:
 *   The current State; the component re-renders on every change.
 */
export function useAppState(): State {
  return useSyncExternalStore(subscribe, getState);
}
