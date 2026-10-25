// Copy and demo data for the landing page, verbatim from the design.

/** Broker names in the marquee: [name, letter-spacing, text-transform]. */
export const BROKERS: [string, string, "none" | "uppercase"][] = [
  ["Pacific Crest Logistics", "0", "none"], ["IRONLINE", ".2em", "uppercase"], ["Bayline Freight", "-0.01em", "none"], ["SUMMIT CARGO", ".1em", "uppercase"],
  ["Redwood Haul Co.", "0", "none"], ["MERIDIAN", ".3em", "uppercase"], ["Granite Lane", "-0.01em", "none"], ["Delta Freight Partners", "0", "none"],
];

export const CAPS: [string, string][] = [
  ["Finds loads", "Load boards and broker emails, filtered to your lanes."],
  ["Negotiates rates", "Calls brokers inside the floor you set."],
  ["Checks rate cons", "Every line against the offer before you sign."],
  ["Dispatches drivers", "WhatsApp and SMS, waits for the confirmation."],
  ["Tracks & reroutes", "ELD and phone location, closures and weather."],
  ["Invoices & chases POD", "Sent the same day the load delivers."],
];

export const CAPTIONS = [
  { tag: "01 — Loading", title: "Dock 3 · Oakland", body: "26 pallets, 38,400 lb. Rate con checked before the first box moved." },
  { tag: "02 — Dispatched", title: "Ava Reed · Truck 101", body: "Driver briefed on WhatsApp. Pickup confirmed, gate code sent." },
  { tag: "03 — In transit", title: "Oakland → Los Angeles", body: "Routed around I-5 roadwork. ETA 16:40, receiver notified." },
  { tag: "04 — Agent", title: "Arjun is on it", body: "While the truck drives, the agent lines up what's next for your yes." },
];

/** Call transcript on the hero's in-scene screen: [who, color, text]. */
export const SCREEN: [string, string, string][] = [
  ["Arjun", "#6FB0FF", "Hi Dana, this is Arjun, an AI dispatcher with Manceps. Truck 101 empties in LA at 17:00. Anything going to Fresno tomorrow?"],
  ["Broker · Granite Lane", "#8FA3BD", "22 pallets, 07:00 pickup in Commerce. $1,350."],
  ["Arjun", "#6FB0FF", "220 miles loaded and we're right there. Can you do $1,550?"],
  ["Broker · Granite Lane", "#8FA3BD", "Meet me at $1,480 and it's yours."],
];

export const TASKS = ["Backhaul ready for your yes · $1,480", "Rate con checked", "Ava briefed on WhatsApp"];

/** Agent log rows: [time, kind, color, text]. */
export const LOG: [string, string, string, string][] = [
  ["06:02", "Search", "#6FB0FF", "Found 14 loads out of Oakland that fit Truck 101."],
  ["06:09", "Call", "#E8D28C", "Called Pacific Crest. Negotiated $2,050 → $2,240."],
  ["06:21", "Check", "#8FD6B0", "Rate con matches the offer: rate, times, 53' dry van."],
  ["06:52", "WhatsApp", "#8FD6B0", "Ava confirmed pickup for 08:00."],
  ["09:40", "Track", "#6FB0FF", "Roadwork on I-5 near Coalinga. Rerouted via CA-33."],
  ["11:15", "Call", "#E8D28C", "Told the receiver ETA 16:40, inside the window."],
  ["13:02", "Search", "#6FB0FF", "Lined up a backhaul LA → Fresno for tomorrow."],
  ["16:44", "Invoice", "#8FD6B0", "Delivered. POD in, invoice sent to Pacific Crest."],
];

export const AGENTS = [
  { name: "Arjun Mehta", role: "The Closer", img: "/assets/agent-d.jpg", blurb: "Quick with numbers and hard to say no to. Pushes every rate a little further." },
  { name: "Mei Lin", role: "The Planner", img: "/assets/agent-c.jpg", blurb: "Thinks three loads ahead. Keeps trucks full and empty miles low." },
  { name: "Amara Okafor", role: "The Steady Hand", img: "/assets/agent-b.jpg", blurb: "Calm on a bad day. Drivers and receivers trust her, so problems get solved fast." },
  { name: "Ethan Cole", role: "The Hustler", img: "/assets/agent-a.jpg", blurb: "Upbeat and always on the boards. First to call when a good load drops." },
];

export const STATUS_LINES = ["3 trucks moving", "On a call · Granite Lane", "Checking a rate con", "Briefing Ava on WhatsApp"];

export interface Step {
  n: string;
  title: string;
  body: string;
  head: string;
  time: string;
}

export const STEPS: Step[] = [
  { n: "01", title: "Finds the load, negotiates it, and asks you to book it", body: "Searches the boards for loads on your lanes, calls the broker, negotiates the rate and checks the rate con line by line. You approve the booking with one tap.", head: "Call · Pacific Crest", time: "02:14" },
  { n: "02", title: "Briefs the driver where they already are", body: "Pickup details, appointment times and the route, sent on WhatsApp. It waits for the confirmation. No new app for drivers.", head: "WhatsApp · Ava Reed", time: "06:48" },
  { n: "03", title: "Watches every mile, fixes what slips", body: "Tracks the truck, calls the receiver when it's running late, reroutes around closures and invoices the moment the POD lands.", head: "Track · Truck 101", time: "09:40" },
];
