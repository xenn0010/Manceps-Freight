// Demo data for surfaces the backend does not serve yet, ported from the Claude Design handoff.
// Every surface that reads from here shows a "Demo" tag. Text with {agent} or {driver} is filled in at render time.
import type { Column, Fact, LngLat, Row, Tone } from "../data";

export type PermKey = "book" | "negotiate" | "brokers" | "drivers" | "reroute" | "sign";
/** Booking loads and signing rate cons always wait for the owner's one-tap approval. */
export type LockedPermKey = "book" | "sign";
export type FreePermKey = Exclude<PermKey, LockedPermKey>;
export type PermLevel = "auto" | "ask" | "off";
export type Perm = Record<FreePermKey, PermLevel> & Record<LockedPermKey, "ask">;
export type PresetKey = "ask" | "balanced" | "auto";

export const LOCKED_PERMS: readonly LockedPermKey[] = ["book", "sign"];

/** A demo truck's headline, used only by the demo fleet model below. */
export interface DemoTruck {
  unit: string;
  driver: string;
  pill: string;
  tone: Tone;
  now: string;
  next: string;
}

export interface LoadDetail {
  lane: string;
  ref: string;
  f: Fact[];
}

export interface DemoTruckDetail {
  load: LoadDetail | null;
  noLoad?: string;
  bookedLoad?: LoadDetail;
  hos: [string, number, number][];
}

/** One scripted call line: who speaks, and the text template. */
export type ScriptLine = ["agent" | "driver", string];

export const DEMO_TRUCK_IDS = ["T-101", "T-102", "T-103", "T-104"] as const;

export const DEMO_TRUCKS: Record<string, DemoTruck> = {
  "T-101": { unit: "101", driver: "Ava Reed", pill: "Unloading", tone: "grey", now: "Vernon, LA", next: "Free at 12:00 · backhaul proposed" },
  "T-102": { unit: "102", driver: "Ben Ortiz", pill: "Running late", tone: "amber", now: "Fresno → Stockton", next: "ETA 15:30 · window 14:00–15:00" },
  "T-103": { unit: "103", driver: "Chloe Chen", pill: "On time", tone: "green", now: "I-80 near Davis", next: "Arrives Oakland 11:30" },
  "T-104": { unit: "104", driver: "Daniel Brooks", pill: "Off duty", tone: "grey", now: "San Jose yard", next: "Back on duty Tue 07:00" },
};

export const DEMO_DETAIL: Record<string, DemoTruckDetail> = {
  "T-101": {
    load: null,
    noLoad: "Proposed: Commerce → SF, Tue 07:00, $2,240.",
    bookedLoad: { lane: "Commerce → San Francisco", ref: "Granite Lane · #GL-55120", f: [["Rate", "$2,240 · $5.86/mi"], ["Miles", "382 loaded · 12 empty"], ["Commodity", "Dry grocery · 22 pallets"], ["Weight", "38,400 lb"], ["Pickup", "Tue 07:00 · Commerce"], ["Delivery", "Tue 15:30 · SF"]] },
    hos: [["Drive left", 8.5, 11], ["Shift left", 11, 14], ["Cycle left", 49, 70]],
  },
  "T-102": {
    load: { lane: "Fresno → Stockton", ref: "Valley Logistics · #VL-30981", f: [["Rate", "$650 · $5.20/mi"], ["Miles", "125 loaded"], ["Commodity", "Produce · 18 pallets"], ["Weight", "36,200 lb · reefer 34°F"], ["Picked up", "Mon 12:30 · Fresno"], ["Delivery", "Mon 15:30 · Stockton"]] },
    hos: [["Drive left", 5.2, 11], ["Shift left", 6.5, 14], ["Cycle left", 31, 70]],
  },
  "T-103": {
    load: { lane: "Sacramento → Oakland", ref: "Delta Freight · #DF-11873", f: [["Rate", "$550 · $6.11/mi"], ["Miles", "90 loaded"], ["Commodity", "Building supplies"], ["Weight", "41,000 lb"], ["Picked up", "Mon 09:00 · Sacramento"], ["Delivery", "Mon 11:30 · Oakland"]] },
    hos: [["Drive left", 9.1, 11], ["Shift left", 12, 14], ["Cycle left", 55, 70]],
  },
  "T-104": {
    load: null,
    noLoad: "Back on duty Tue 07:00. Looking for a load out of San Jose.",
    hos: [["Reset", 6, 10], ["Shift left", 14, 14], ["Cycle left", 62, 70]],
  },
};

export const LCOLS: Column[] = [["id", "Load", 92], ["truck", "Truck", 64, "c"], ["driver", "Driver", 124], ["lane", "Lane", 220], ["pickup", "Pickup", 108], ["delivery", "Delivery", 108], ["miles", "Miles", 72, "r"], ["rate", "Rate", 92, "r"], ["rpm", "$/mi", 76, "r"], ["broker", "Broker", 136], ["status", "Status", 136], ["notes", "Notes", 260]];

const load = (id: string, truck: string, driver: string, lane: string, pickup: string, delivery: string, miles: number | "", rate: number | "", broker: string, status: string, notes: string): Row =>
  ({ id, truck, driver, lane, pickup, delivery, miles, rate, broker, status, notes, flag: false });

export const LOADS0: Row[] = [
  load("L-30981", "102", "Ben Ortiz", "Fresno → Stockton", "Mon 12:30", "Mon 15:30", 125, 650, "Valley Logistics", "In transit", "Window moved to 15:30"),
  load("L-11873", "103", "Chloe Chen", "Sacramento → Oakland", "Mon 09:00", "Mon 11:30", 90, 550, "Delta Freight", "In transit", ""),
  load("L-24410", "101", "Ava Reed", "San Francisco → Los Angeles", "Sun 18:00", "Mon 08:40", 382, 1200, "Coastline", "Delivered", "POD received"),
  load("L-55120", "101", "Ava Reed", "Commerce → San Francisco", "Tue 07:00", "Tue 15:30", 382, 2240, "Granite Lane", "Needs your yes", "Negotiated up from $2,050"),
  load("—", "104", "Daniel Brooks", "", "Tue 07:00", "", "", "", "", "Open", ""),
  load("—", "103", "Chloe Chen", "", "Mon 13:00", "", "", "", "", "Open", ""),
  load("L-30422", "102", "Ben Ortiz", "Stockton → Sacramento", "Tue 06:00", "Tue 08:30", 48, 380, "Valley Logistics", "Offer", ""),
  load("L-19007", "103", "Chloe Chen", "Oakland → Reno", "Tue 08:00", "Tue 13:00", 218, 1640, "Sierra Freight", "Offer", ""),
  load("L-20981", "104", "Daniel Brooks", "Fresno → Los Angeles", "Wed 06:00", "Wed 11:30", 220, 680, "Westline", "Offer", ""),
  load("L-22110", "101", "Ava Reed", "San Francisco → Sacramento", "Wed 09:00", "Wed 11:00", 88, 410, "Bayline", "Offer", ""),
];

/** Backhauls the agent finds for the open rows, keyed by row index in LOADS0. */
export const BACKHAUL: Record<number, Row> = {
  4: { id: "L-41207", lane: "San Jose → Sacramento", delivery: "Tue 09:30", miles: 120, rate: 780, broker: "Delta Freight", notes: "Found on DAT · fits Daniel's hours" },
  5: { id: "L-41388", lane: "Oakland → Stockton", delivery: "Mon 15:00", miles: 74, rate: 520, broker: "BayFreight", notes: "12 empty mi from delivery" },
};

/** Demo drivers matching the demo loads; the live drivers sheet never shows them. */
export const DEMO_DRIVERS: Row[] = [
  { driver: "Ava Reed", truck: "101", phone: "(415) 555-0142", duty: "On duty", checkin: "08:40 · WhatsApp", notes: "" },
  { driver: "Ben Ortiz", truck: "102", phone: "(559) 555-0177", duty: "Driving", checkin: "10:12 · Call", notes: "" },
  { driver: "Chloe Chen", truck: "103", phone: "(916) 555-0109", duty: "Driving", checkin: "09:48 · WhatsApp", notes: "" },
  { driver: "Daniel Brooks", truck: "104", phone: "(408) 555-0163", duty: "Off duty", checkin: "Sun 19:00 · Text", notes: "" },
];

export const DISPATCHES: [string, LngLat][] = [
  ["New offer · Oakland → Reno · $1,640", [-122.2711, 37.8044]],
  ["{agent} called Delta Freight about #104", [-121.8863, 37.3382]],
  ["Load posted · Fresno → LA · $1,980", [-119.7871, 36.7378]],
  ["Ava confirmed she's done unloading", [-118.2301, 34.0039]],
  ["Rate check · Sacramento lanes up 6%", [-121.4944, 38.5816]],
];

/** Scripted agent calls. The agent's first line always says it is an AI, as it must with any outside party. */
export const SCRIPTS: ScriptLine[][] = [
  [["agent", "Hi {driver}, it's {agent}, the AI dispatcher. You nearly empty at Vernon?"], ["driver", "Last pallet's coming off now."], ["agent", "I've got Commerce to San Francisco tomorrow, 07:00, $2,240. It's waiting on your dispatcher's yes."], ["driver", "Works for me. I'll reset here tonight."], ["agent", "Perfect. Rate con and dock info come to your WhatsApp once it's approved."]],
  [["agent", "Hi {driver}, it's {agent}, the AI dispatcher. Stockton moved your window to 15:30."], ["driver", "Nice, that takes the pressure off. Just past Merced."], ["agent", "Turlock weigh station's open, no line right now."], ["driver", "Copy. Fuel's good, I'll go straight through."], ["agent", "Great. I'll text you the new dock number."]],
  [["agent", "Hi {driver}, it's {agent}, the AI dispatcher. Quick heads up: traffic at the Carquinez Bridge."], ["driver", "How bad?"], ["agent", "About 15 minutes. You'll still make 11:30, so no reroute."], ["driver", "Sounds good, thanks."]],
  [["agent", "Hi {driver}, it's {agent}, the AI dispatcher. Sorry to bug you on your reset."], ["driver", "No worries. What's up?"], ["agent", "San Jose to Sacramento Tuesday 07:00, $780. Want me to send it to your dispatcher for a yes?"], ["driver", "Yeah, send it."], ["agent", "Done. Enjoy the rest of your evening."]],
];

export const PERMS: [PermKey, string, string][] = [
  ["book", "Book loads", "Accept offers that fit your lanes and drivers' hours"],
  ["negotiate", "Negotiate rates", "Counter brokers, never below your floor"],
  ["brokers", "Call brokers & shippers", "Find loads, check status, fix appointments"],
  ["drivers", "Call & text drivers", "Updates, check-ins, new load details"],
  ["reroute", "Reroute trucks", "Around traffic, closures, weather"],
  ["sign", "Sign rate confirmations", "Using your company signature"],
];

export const PRESETS: Record<PresetKey, [string, string, Perm]> = {
  ask: ["Ask me first", "Suggests everything, you decide", { book: "ask", negotiate: "ask", brokers: "auto", drivers: "ask", reroute: "ask", sign: "ask" }],
  balanced: ["Balanced", "Routine work on its own, money waits for you", { book: "ask", negotiate: "ask", brokers: "auto", drivers: "auto", reroute: "auto", sign: "ask" }],
  auto: ["Autopilot", "Runs the rest; booking and signing still wait for you", { book: "ask", negotiate: "auto", brokers: "auto", drivers: "auto", reroute: "auto", sign: "ask" }],
};

export const ANSWERS: Record<string, string> = {
  "Find a load for 104": "Daniel's back Tue 07:00 in San Jose. Best fit: San Jose → Sacramento, $780, 120 mi with Delta Freight. Want me to send it to you for a yes?",
  "Is 102 on time?": "Running about 30 min late. I've asked Stockton to move the window to 15:30–16:30 and I'll call them at 11:00 if they don't answer.",
  "What did you do today?": "Found 1 load, negotiated $190 more on another, rerouted 103 around I-80 traffic, and briefed Ava on WhatsApp. One thing needs you: the 101 backhaul.",
};

export const FALLBACK_ANSWER = "On it. I'll check the boards and your drivers' hours and get back to you in a minute.";

/** The backhaul load the "Needs your yes" card books. */
export const BACKHAUL_101_ID = "L-55120";
export const BACKHAUL_101_RATE = 2240;
