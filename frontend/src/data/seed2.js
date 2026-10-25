// Phase 2 seed additions: execution timeline, delay history, driver threads, rules.
const ev = (id, at, kind, tripId, truckId, source, text, extra = {}) => ({ id, at, kind, tripId, truckId, source, text, status: "pending", ...extra });

const EVENTS = [
  ev("EV-01", 690, "delivered", "L-301", "T-103", "Driver call", "Chloe Chen delivered L-301 in Oakland · 11:30"),
  ev("EV-02", 700, "pod", "L-301", "T-103", "Driver text", "POD received for L-301"),
  ev("EV-03", 720, "released", "L-101", "T-101", "Driver text", "Truck 101 released in Vernon · L-101 POD received"),
  ev("EV-04", 750, "picked_up", "L-201", "T-102", "Driver call", "Ben Ortiz loaded L-201 · departed Fresno"),
  ev("EV-05", 870, "in_transit", "L-201", "T-102", "Driver text", "L-201 in transit near Merced"),
  ev("EV-06", 930, "delivered", "L-201", "T-102", "Driver call", "Ben Ortiz delivered L-201 in Stockton · 15:30"),
  ev("EV-07", 955, "pod", "L-201", "T-102", "Driver text", "POD received for L-201"),
  ev("EV-08", 1860, "on_duty", null, "T-104", "Driver text", "Daniel Brooks back on duty in San Jose"),
  ev("EV-09", 1950, "picked_up", "L-102", "T-101", "Driver text", "Ava Reed picked up L-102 in Carson"),
  ev("EV-10", 2160, "in_transit", "L-102", "T-101", "Driver call", "L-102 in transit on I-5 near Kettleman City"),
  ev("EV-11", 2400, "delivered", "L-102", "T-101", "Driver call", "Ava Reed delivered L-102 in Oakland · 16:00"),
  ev("EV-12", 2415, "pod", "L-102", "T-101", "Driver text", "POD received for L-102"),
];

const thread = (id, name, unit, messages) => ({
  id, kind: "driver_thread", title: `${name} · Truck ${unit}`, counterpart: `${name} · Driver`, channel: "SMS / calls (simulated)",
  objective: "Track execution updates and documents", messages, source: "driver",
});

export function applyPhase2(seed) {
  seed.events = EVENTS.map((e) => ({ ...e }));
  seed.rules = {};
  seed.corrections = [];
  seed.trips["L-201"].delayHistory = [
    { at: 540, label: "Original window", value: "Mon 14:00–15:00", source: "Rate confirmation" },
    { at: 570, label: "Loading delayed", value: "Shipper short on labour · release 12:30", source: "Driver call (Ben Ortiz)" },
    { at: 575, label: "Revised appointment requested", value: "Asked for 15:30–16:30", source: "AI email to broker" },
  ];
  seed.proposals["P-1"].versions = [{ version: 1, rate: 1100, at: 582, source: "Broker offer" }];
  seed.conversations["CONV-DRV-101"].objective = "Return-load instructions and execution updates";
  seed.conversations["CONV-DRV-102"] = thread("CONV-DRV-102", "Ben Ortiz", "102", [
    { id: "M-D102-1", from: "driver", at: 570, text: "Shipper is short on labour, they say release around 12:30." },
  ]);
  seed.conversations["CONV-DRV-103"] = thread("CONV-DRV-103", "Chloe Chen", "103", [
    { id: "M-D103-1", from: "driver", at: 585, text: "Passing Davis, all good. ETA Oakland 11:30." },
  ]);
  seed.search104 = {
    progress: "Checking 3 boards · Waiting on one broker",
    steps: [
      { label: "DAT, Truckstop, Direct broker list", status: "done" },
      { label: "Bay Produce asked for written rate", status: "waiting" },
    ],
    candidate: { lane: "San Jose → Sacramento", window: "Tue 08:00–10:00", rate: 780, broker: "Bay Produce Co." },
  };
  seed.aiTasks["TASK-104"].text = "Finding loads for Truck 104";
  seed.notifications.push({
    id: "N-U-104C", key: "seed-n6", group: "updates", title: "Candidate for Truck 104", body: "SJ → Sacramento Tue 08:00 · $780 · info only",
    link: { type: "activity", id: null }, at: 598, read: false, status: "open", createdAt: "2026-10-26T17:00:00.000Z",
  });
  return seed;
}
