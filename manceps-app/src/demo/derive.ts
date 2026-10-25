// Demo: derived text and numbers for surfaces without a backend yet (needs card, weekly dashboard, permissions).
import { DEFAULT_AGENT_NAME } from "../agents";
import { TONE, type Tone } from "../data";
import type { State } from "../store";
import { DEMO_DETAIL, DEMO_TRUCKS, PRESETS, type LoadDetail, type Perm, type PresetKey } from "./data";

export interface Need {
  id: "b101" | "r102";
  c: string;
  tag: string;
  title: string;
  body: string;
  yesLabel: string;
}

/** Weekly booked revenue (USD) per weekday before the 101 backhaul is booked. */
const WEEK_BASE: [string, number][] = [["M", 1200], ["T", 650], ["W", 1850], ["T", 0], ["F", 0], ["S", 0], ["S", 0]];
/** Bar chart scale: revenue that fills the full bar height. */
const WEEK_BAR_MAX_USD = 3000;
const WEEK_BAR_MAX_PX = 46;
const WEEK_BAR_MIN_PX = 4;
const BACKHAUL_USD = 2240;
/** Hours-of-service bars turn amber below this fraction remaining. */
const HOS_LOW = 0.3;

/**
 * List the decisions waiting on the user, in priority order.
 *
 * Args:
 *   s: Current state.
 *   agent: The agent's display name.
 *
 * Returns:
 *   Every open need, including ones snoozed with Later.
 */
export function allNeeds(s: Pick<State, "booked" | "r102">, agent: string = DEFAULT_AGENT_NAME): Need[] {
  const all: Need[] = [];
  if (!s.booked) all.push({ id: "b101", c: "#2272AD", tag: "Needs your yes", title: "Book a $2,240 backhaul for 101?", body: "Commerce → San Francisco, Tue 07:00. Granite Lane. $5.86/mi, 12 empty miles. " + agent + " negotiated it up from $2,050.", yesLabel: "Book it" });
  if (!s.r102) all.push({ id: "r102", c: "#E39A2D", tag: "Heads up", title: "102 is running 30 min late", body: agent + " already asked Stockton to move the window. Nothing to do unless you want to call them yourself.", yesLabel: "Got it" });
  return all;
}

/**
 * Name of the preset matching the current permissions.
 *
 * Args:
 *   perm: Current permissions.
 *
 * Returns:
 *   The preset name, or "Custom" when none matches exactly.
 */
export function presetName(perm: Perm): string {
  const hit = (Object.keys(PRESETS) as PresetKey[]).find((k) => presetMatches(k, perm));
  return hit ? PRESETS[hit][0] : "Custom";
}

/**
 * Whether a preset matches the current permissions exactly.
 *
 * Args:
 *   key: Preset key.
 *   perm: Current permissions.
 *
 * Returns:
 *   True when every field equals the preset.
 */
export function presetMatches(key: PresetKey, perm: Perm): boolean {
  const val = PRESETS[key][2];
  return (Object.keys(val) as (keyof Perm)[]).every((k) => val[k] === perm[k]);
}

/**
 * Bars for the account panel's weekly chart.
 *
 * Args:
 *   booked: Whether the 101 backhaul is booked (adds $2,240 to Tuesday).
 *
 * Returns:
 *   One bar per weekday with label, height and color.
 */
export function weekBars(booked: boolean): { d: string; h: string; c: string }[] {
  return WEEK_BASE.map(([d, base], i) => {
    const v = base + (i === 1 && booked ? BACKHAUL_USD : 0);
    const h = Math.max(WEEK_BAR_MIN_PX, Math.round((v / WEEK_BAR_MAX_USD) * WEEK_BAR_MAX_PX)) + "px";
    return { d, h, c: i === 1 && booked ? "#2272AD" : v ? "#010D1D" : "#E2E8F0" };
  });
}

/**
 * The four stat tiles in the account panel.
 *
 * Args:
 *   s: Current state.
 *   agent: The agent's display name.
 *
 * Returns:
 *   Key/value pairs in display order.
 */
export function weekStats(s: Pick<State, "booked" | "r102">, agent: string = DEFAULT_AGENT_NAME): { k: string; v: string }[] {
  return [
    { k: "Profit / mile", v: s.booked ? "$2.41" : "$2.18" },
    { k: "Empty miles", v: s.booked ? "3.9%" : "3.7%" },
    { k: "On-time", v: s.r102 ? "100%" : "92%" },
    { k: agent + " saved you", v: "11 h" },
  ];
}

/**
 * Booked revenue this week and how it compares with last week.
 *
 * Args:
 *   booked: Whether the 101 backhaul is booked.
 *
 * Returns:
 *   Total, comparison line and whether the comparison is good news.
 */
export function weekTotal(booked: boolean): { total: string; delta: string; up: boolean } {
  return booked ? { total: "$5,940", delta: "+$1,180 vs last week", up: true } : { total: "$3,700", delta: "−$1,060 vs last week · 2 days left", up: false };
}

/**
 * Header text for a demo truck: status pill, colors and the "next" line.
 *
 * Args:
 *   id: Demo truck id.
 *   s: Current state.
 *
 * Returns:
 *   Pill label, pill colors and the next-step text.
 */
export function truckHeadline(id: string, s: Pick<State, "booked" | "r102">): { pill: string; pillBg: string; pillInk: string; next: string } {
  const t = DEMO_TRUCKS[id];
  if (!t) return { pill: "", pillBg: TONE.grey[0], pillInk: TONE.grey[1], next: "" };
  const fixed102 = id === "T-102" && s.r102;
  const tone: Tone = fixed102 ? "green" : t.tone;
  const next = fixed102 ? "New window 15:30–16:30 · on time" : id === "T-101" && s.booked ? "Booked · Commerce → SF Tue 07:00" : t.next;
  return { pill: fixed102 ? "On time" : t.pill, pillBg: TONE[tone][0], pillInk: TONE[tone][1], next };
}

/**
 * The load a demo truck is on, counting the 101 backhaul once booked.
 *
 * Args:
 *   id: Demo truck id.
 *   booked: Whether the 101 backhaul is booked.
 *
 * Returns:
 *   The load detail, or null when the truck has none.
 */
export function truckLoad(id: string, booked: boolean): LoadDetail | null {
  const d = DEMO_DETAIL[id];
  if (!d) return null;
  return d.load ?? (id === "T-101" && booked ? d.bookedLoad ?? null : null);
}

/**
 * Hours-of-service bars for a demo truck's driver.
 *
 * Args:
 *   id: Demo truck id.
 *
 * Returns:
 *   Label, value text, bar width and color per bar.
 */
export function hosBars(id: string): { k: string; v: string; w: string; c: string }[] {
  return (DEMO_DETAIL[id]?.hos ?? []).map(([k, v, max]) => ({ k, v: v + " h", w: Math.round((v / max) * 100) + "%", c: v / max < HOS_LOW ? "#E39A2D" : "#2272AD" }));
}
