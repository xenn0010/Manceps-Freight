import geo from "./routeGeometry.json";
import { bearing, nearestIndex } from "./geo";
import { applyPhase2 } from "./seed2";
import { applyPhase3 } from "./seed3";
import { applyPhase4 } from "./seed4";

export const COST_PER_MILE = 1.8;
export const START_CLOCK = 600; // minutes since Mon 26 Oct 2026 00:00 PT
export const SCHEMA_VERSION = 4;
export const ROUTES = geo;

const R = (id) => geo[id].coordinates;
const first = (id) => R(id)[0];
const last = (id) => R(id)[R(id).length - 1];

const L301 = R("R-L301");
export const T103_PROGRESS = nearestIndex(L301, [-121.74, 38.545]);

const SEED_ISO = "2026-10-26T17:00:00.000Z";
const meta = (source = "seed") => ({ source, createdAt: SEED_ISO, updatedAt: SEED_ISO });

const trucks = {
  "T-101": {
    id: "T-101", unit: "101", driverId: "D-101", carrierId: "CAR-1", equipment: "53' dry van",
    position: [-118.2301, 34.0039], heading: 320, health: "working",
    status: "Unloading in Los Angeles", statusShort: "Unloading · LA", pill: "Unloading",
    location: "Vernon, Los Angeles", truckAvailableAt: "Mon 12:00", currentTripId: "L-101", ...meta(),
  },
  "T-102": {
    id: "T-102", unit: "102", driverId: "D-102", carrierId: "CAR-1", equipment: "53' dry van",
    position: first("R-L201"), heading: bearing(R("R-L201")[0], R("R-L201")[3]), health: "risk",
    status: "Loading delayed in Fresno", statusShort: "Delivery at risk", pill: "At risk",
    location: "Fresno shipper", truckAvailableAt: "Mon 12:30 (after loading)", currentTripId: "L-201", ...meta(),
  },
  "T-103": {
    id: "T-103", unit: "103", driverId: "D-103", carrierId: "CAR-1", equipment: "53' dry van",
    position: L301[T103_PROGRESS], heading: bearing(L301[T103_PROGRESS], L301[T103_PROGRESS + 2]), health: "on_track",
    status: "In transit near Davis", statusShort: "On track · ETA 11:30", pill: "In transit",
    location: "I-80 near Davis", truckAvailableAt: "Mon 11:30 (after delivery)", currentTripId: "L-301", ...meta(),
  },
  "T-104": {
    id: "T-104", unit: "104", driverId: "D-104", carrierId: "CAR-1", equipment: "53' dry van",
    position: [-121.8863, 37.3382], heading: 300, health: "idle",
    status: "Off duty in San Jose", statusShort: "Off duty until Tue 07:00", pill: "Off duty",
    location: "San Jose yard", truckAvailableAt: "Now (parked)", currentTripId: null, ...meta(),
  },
};

const drivers = {
  "D-101": { id: "D-101", name: "Ava Reed", truckId: "T-101", availableAt: "Tue 07:00", dutyNote: "10 h break after L-101", ...meta() },
  "D-102": { id: "D-102", name: "Ben Ortiz", truckId: "T-102", availableAt: "On duty", dutyNote: "Waiting at shipper", ...meta() },
  "D-103": { id: "D-103", name: "Chloe Chen", truckId: "T-103", availableAt: "On duty", dutyNote: "Driving", ...meta() },
  "D-104": { id: "D-104", name: "Daniel Brooks", truckId: "T-104", availableAt: "Tue 07:00", dutyNote: "Off duty", ...meta() },
};

const trips = {
  "L-101": {
    id: "L-101", truckId: "T-101", origin: "San Francisco", destination: "Los Angeles", status: "active", phase: "Unloading",
    revenue: 1200, loadedMiles: 400, emptyMiles: 15, sortKey: 0, broker: "Golden Gate Freight",
    pickup: { place: "San Francisco", window: "Sun 25 Oct 14:00" }, delivery: { place: "Vernon, LA", window: "Mon 09:00–11:00" },
    routes: [], stops: [], ...meta(),
  },
  "L-103": {
    id: "L-103", truckId: "T-101", origin: "San Francisco", destination: "Los Angeles", status: "confirmed", phase: "Confirmed",
    protected: true, revenue: 1300, loadedMiles: 400, emptyMiles: 10, sortKey: 2 * 1440 + 480, broker: "Bayline Brokerage",
    pickup: { place: "San Francisco", window: "Wed 08:00–09:00" }, delivery: { place: "Los Angeles", window: "Wed 16:00–18:00" },
    routes: [{ id: "R-L103", kind: "loaded" }],
    stops: [
      { type: "pickup", coord: first("R-L103"), label: "PU Wed 08:00" },
      { type: "delivery", coord: last("R-L103"), label: "DEL Wed 16:00" },
    ],
    ...meta(),
  },
  "L-201": {
    id: "L-201", truckId: "T-102", origin: "Fresno", destination: "Stockton", status: "active", phase: "Loading (delayed)",
    revenue: 650, loadedMiles: 140, emptyMiles: 10, sortKey: 0, broker: "Central Valley Brokers",
    pickup: { place: "Fresno", window: "Release Mon 12:30" }, delivery: { place: "Stockton", window: "Mon 14:00–15:00" },
    eta: "Mon 15:30",
    risk: { release: "12:30", eta: "15:30", window: "14:00–15:00", note: "Revised appointment requested", requested: "15:30–16:30" },
    routes: [{ id: "R-L201", kind: "loaded" }],
    stops: [
      { type: "pickup", coord: first("R-L201"), label: "PU Fresno" },
      { type: "delivery", coord: last("R-L201"), label: "DEL 14:00" },
    ],
    ...meta(),
  },
  "L-301": {
    id: "L-301", truckId: "T-103", origin: "Sacramento", destination: "Oakland", status: "active", phase: "In transit",
    revenue: 550, loadedMiles: 90, emptyMiles: 5, sortKey: 0, broker: "Delta Freight Partners",
    pickup: { place: "Sacramento", window: "Mon 09:00 (done)" }, delivery: { place: "Oakland", window: "Mon 11:00–13:00" },
    eta: "Mon 11:30", progressMiles: 22,
    routes: [{ id: "R-L301", kind: "loaded", progressIndex: T103_PROGRESS }],
    stops: [{ type: "delivery", coord: last("R-L301"), label: "DEL 11:00" }],
    ...meta(),
  },
};

const segments = {
  "SEG-101-RET": {
    id: "SEG-101-RET", truckId: "T-101", type: "empty_return", origin: "Los Angeles", destination: "San Francisco",
    miles: 400, status: "planned", routeId: "R-L101-RET", replacedByOfferId: "O-1", sortKey: 1440 + 420,
    reason: "Required to reach SF for protected L-103", ...meta("ai"),
  },
};

const offers = {
  "O-1": {
    id: "O-1", truckId: "T-101", tripId: "L-102", broker: "Demo Pacific Broker", contact: "Maya Lin",
    origin: "Los Angeles", destination: "Oakland", rate: 1100, equipment: "53' dry van", commodity: "Packaged goods", weight: 30000,
    pickup: { place: "Carson, Los Angeles", window: "Tue 08:00–09:00" }, delivery: { place: "Oakland", window: "Tue 16:00–17:00" },
    loadedMiles: 400, emptyToPickup: 12, emptyAfter: 18, arriveSf: "Tue 18:00", restHours: 10, bufferHours: 4,
    sortKey: 1440 + 480, status: "proposed", documentId: "DOC-RC-1", conversationId: "CONV-O1",
    routes: [
      { id: "R-O1-EMPTY-PU", kind: "empty" },
      { id: "R-O1-LOADED", kind: "loaded" },
      { id: "R-O1-EMPTY-SF", kind: "empty" },
    ],
    stops: [
      { type: "pickup", coord: first("R-O1-LOADED"), label: "PU Tue 08:00" },
      { type: "delivery", coord: last("R-O1-LOADED"), label: "DEL Tue 16:00" },
    ],
    ...meta("broker"),
  },
  "O-2": {
    id: "O-2", truckId: "T-101", broker: "Desert Line Logistics", origin: "Los Angeles", destination: "Phoenix", rate: 1600,
    pickup: { place: "Los Angeles", window: "Tue 10:00" }, delivery: { place: "Phoenix", window: "Wed 09:00" },
    status: "unsuitable", reason: "Wednesday delivery in Phoenix conflicts with L-103 (SF pickup Wed 08:00–09:00).",
    ...meta("broker"),
  },
};

const proposals = {
  "P-1": {
    id: "P-1", offerId: "O-1", truckId: "T-101", version: 1, status: "proposal_ready", driverStatus: "none",
    handledBy: "ai", approvals: [], callId: null, statusChangedAt: 0, driverStatusAt: 0,
    history: [{ status: "proposal_ready", at: 595 }], rejectReason: null, changeNote: null,
    alternatives: ["O-2"], replacesSegmentId: "SEG-101-RET", ...meta("ai"),
  },
};

const documents = {
  "DOC-RC-1": {
    id: "DOC-RC-1", kind: "rate_confirmation", title: "Rate confirmation · O-1", from: "Demo Pacific Broker",
    fileName: "RateCon_O-1_DemoPacific.pdf", receivedAt: 591, status: "received", matches: true,
    fields: [
      { label: "Rate", offer: "$1,100 all-in", written: "$1,100 all-in" },
      { label: "Pickup", offer: "Tue 08:00–09:00 · Carson, LA", written: "Tue 08:00–09:00 · Carson, LA" },
      { label: "Delivery", offer: "Tue 16:00–17:00 · Oakland", written: "Tue 16:00–17:00 · Oakland" },
      { label: "Equipment", offer: "53' dry van", written: "53' dry van" },
      { label: "Commodity", offer: "Packaged goods", written: "Packaged goods" },
      { label: "Weight", offer: "30,000 lb", written: "30,000 lb" },
    ],
    ...meta("broker"),
  },
};

const conversations = {
  "CONV-O1": {
    id: "CONV-O1", kind: "broker_thread", title: "Demo Pacific Broker · O-1", counterpart: "Maya Lin · Demo Pacific Broker",
    channel: "Email (simulated)",
    messages: [
      { id: "M-O1-1", from: "broker", at: 582, text: "Hi, I have a Tue LA→Oakland dry van: packaged goods, 30,000 lb. PU 08:00–09:00 Carson, DEL 16:00–17:00 Oakland. $1,100 all-in." },
      { id: "M-O1-2", from: "ai", at: 584, text: "Thanks Maya. Truck 101 (53' dry van) fits. Can you send written terms?" },
      { id: "M-O1-3", from: "broker", at: 591, text: "Rate confirmation attached.", attachment: { type: "document", id: "DOC-RC-1", label: "RateCon_O-1_DemoPacific.pdf" } },
    ],
    ...meta("broker"),
  },
  "CONV-DRV-101": {
    id: "CONV-DRV-101", kind: "driver_thread", title: "Ava Reed · Truck 101", counterpart: "Ava Reed · Driver", channel: "SMS (simulated)",
    messages: [{ id: "M-D101-1", from: "driver", at: 552, text: "At the consignee in Vernon, unloading now." }],
    ...meta("driver"),
  },
};

const attention = {
  "ATT-102": {
    id: "ATT-102", kind: "risk", severity: "high", title: "Delivery at risk", truckId: "T-102", priority: 1,
    summary: "ETA 15:30 vs window 14:00–15:00", link: { type: "truck", id: "T-102" }, status: "open", ...meta("ai"),
  },
  "ATT-101": {
    id: "ATT-101", kind: "decision", severity: "info", title: "Return load ready", truckId: "T-101", priority: 2,
    summary: "+$1,046 vs empty return", link: { type: "decision", id: "P-1" }, status: "open", ...meta("ai"),
  },
};

const activity = [
  { seq: 1, at: 552, source: "driver", text: "Ava Reed unloading L-101 in Vernon, LA", link: { type: "thread", id: "CONV-DRV-101" } },
  { seq: 2, at: 560, source: "ai", text: "Started load search for Truck 104 · 2 brokers contacted", link: { type: "truck", id: "T-104" } },
  { seq: 3, at: 575, source: "ai", text: "Requested revised appointment for L-201", link: { type: "truck", id: "T-102" } },
  { seq: 4, at: 582, source: "broker", text: "Broker offered $1,100 · LA→Oakland Tue", link: { type: "thread", id: "CONV-O1" } },
  { seq: 5, at: 588, source: "ai", text: "Ruled out LA→Phoenix $1,600 · conflicts with L-103", link: { type: "decision", id: "P-1" } },
  { seq: 6, at: 591, source: "broker", text: "Rate confirmation received · terms match offer", link: { type: "document", id: "DOC-RC-1" } },
  { seq: 7, at: 595, source: "ai", text: "Return load ready for your approval · Truck 101", link: { type: "decision", id: "P-1" } },
].map((a) => ({ ...a, id: `ACT-${a.seq}`, key: `seed-${a.seq}`, createdAt: SEED_ISO }));

const notifications = [
  { id: "N-ATT-102", key: "seed-n1", group: "needs_you", title: "Delivery at risk · Truck 102", body: "Loading delayed · ETA 15:30 misses 14:00–15:00", link: { type: "truck", id: "T-102" }, at: 575, read: false, status: "open" },
  { id: "N-ATT-101", key: "seed-n2", group: "needs_you", title: "Return load ready · Truck 101", body: "Approve O-1 · LA→Oakland $1,100", link: { type: "decision", id: "P-1" }, at: 595, read: false, status: "open" },
  { id: "N-U-1", key: "seed-n3", group: "updates", title: "Truck 103 on track", body: "ETA 11:30 Oakland · window 11:00–13:00", link: { type: "truck", id: "T-103" }, at: 585, read: false, status: "open" },
  { id: "N-U-2", key: "seed-n4", group: "updates", title: "Rate confirmation received", body: "O-1 written terms match offer", link: { type: "document", id: "DOC-RC-1" }, at: 591, read: false, status: "open" },
  { id: "N-U-3", key: "seed-n5", group: "updates", title: "Truck 104 off duty", body: "Daniel Brooks back Tue 07:00 · AI searching", link: { type: "truck", id: "T-104" }, at: 560, read: true, status: "open" },
].map((n) => ({ ...n, createdAt: SEED_ISO }));

export function createSeed() {
  return applyPhase4(applyPhase3(applyPhase2(JSON.parse(
    JSON.stringify({
      schemaVersion: SCHEMA_VERSION,
      seq: 100,
      carrier: { id: "CAR-1", name: "Demo West Freight", costPerMile: COST_PER_MILE, ...meta() },
      trucks, drivers, trips, segments, offers, proposals, documents, conversations, attention,
      calls: {}, activity, notifications,
      aiTasks: {
        "TASK-104": { id: "TASK-104", text: "Finding loads for Truck 104", status: "running", truckId: "T-104" },
        "TASK-L201": { id: "TASK-L201", text: "Waiting on one broker", status: "waiting", truckId: "T-102" },
      },
    })
  ))));
}
