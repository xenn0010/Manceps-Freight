import { log, notify } from "./engine2";
import { CITY_COORDS, placeNear, roadMiles } from "../lib/cities";
import { formatWindow, parseWindow } from "../lib/windows";

// Phase 3 transitions: fleet record edits, guided intake creation, AI settings and rules.
const iso = () => new Date().toISOString();
const COLLECTION = { carrier: "carriers", truck: "trucks", driver: "drivers", trip: "trips" };
const LABELS = {
  name: "name", contactName: "contact", phone: "phone", email: "email", homeBase: "home base", preferredLanes: "preferred lanes",
  maxDeadhead: "max deadhead", minRatePerMile: "min rate/mi", avoidRegions: "avoid regions", unit: "unit", carrierId: "carrier",
  equipment: "equipment", location: "location", opStatus: "operational status", truckAvailableAt: "truck availability",
  costPerMile: "cost/mi", truckId: "assigned truck", availableAt: "driver availability", homeLocation: "home location",
  preferences: "preferences", origin: "origin", destination: "destination", pickup: "pickup window", delivery: "delivery window",
  status: "status", revenue: "rate", broker: "broker", commodity: "commodity", weight: "weight", protected: "protected flag",
};

export const recordOf = (data, type, id) => (type === "carrier" && id === data.carrier.id ? data.carrier : data[COLLECTION[type]]?.[id]);
const titleOf = (data, type, r) =>
  ({ carrier: r.name, truck: `Truck ${r.unit}`, driver: r.name, trip: r.id })[type];
const linkOf = (type, r) => (type === "truck" ? { type: "truck", id: r.id } : type === "trip" ? { type: "truck", id: r.truckId } : type === "driver" && r.truckId ? { type: "truck", id: r.truckId } : null);

function relinkDriver(data, drv, truckId) {
  const newTruck = data.trucks[truckId];
  if (!newTruck || newTruck.driverId === drv.id) return;
  const oldTruck = data.trucks[drv.truckId];
  const other = data.drivers[newTruck.driverId];
  newTruck.driverId = drv.id;
  if (other) {
    other.truckId = oldTruck ? oldTruck.id : null;
    if (oldTruck) oldTruck.driverId = other.id;
  }
}

function syncTrip(t) {
  const pw = parseWindow(t.pickup.window);
  const dw = parseWindow(t.delivery.window);
  if (pw) t.sortKey = pw.startMin;
  t.stops.forEach((s) => {
    if (s.type === "pickup" && pw) s.label = `PU ${pw.day} ${pw.start}`;
    if (s.type === "delivery" && dw) s.label = `DEL ${dw.day} ${dw.start}`;
  });
}

export function saveRecord(d, type, id, patch) {
  const rec = recordOf(d.data, type, id);
  if (!rec) return false;
  const changed = Object.keys(patch).filter((k) => JSON.stringify(rec[k] ?? "") !== JSON.stringify(patch[k] ?? ""));
  if (!changed.length) return false;
  if (type === "driver" && patch.truckId) relinkDriver(d.data, rec, patch.truckId);
  Object.assign(rec, patch, { updatedAt: iso(), source: "dispatcher" });
  if (type === "trip") syncTrip(rec);
  if (type === "truck" && changed.includes("location") && !rec.currentTripId && CITY_COORDS[rec.location]) rec.position = placeNear(d.data.trucks, rec.location, rec.id);
  d.data.seq += 1;
  log(d, `edit-${d.data.seq}`, { source: "dispatcher", text: `Updated ${titleOf(d.data, type, rec)}: ${changed.map((k) => LABELS[k] || k).join(", ")}`, link: linkOf(type, rec) });
  return true;
}

const meta = () => ({ source: "intake", createdAt: iso(), updatedAt: iso() });

const CREATE = {
  truck(d, f) {
    const { trucks, drivers } = d.data;
    if (Object.values(trucks).some((t) => t.unit === f.unit)) return null;
    const id = `T-${f.unit}`;
    d.data.seq += 1;
    const did = drivers[`D-${f.unit}`] ? `D-${d.data.seq}` : `D-${f.unit}`;
    drivers[did] = { id: did, name: f.driverName.trim(), phone: f.driverPhone, truckId: id, availableAt: f.driverAvailableAt, homeLocation: f.location, preferences: "", dutyNote: "Added via intake", ...meta() };
    trucks[id] = {
      id, unit: f.unit, driverId: did, carrierId: d.data.carrier.id, equipment: f.equipment, position: placeNear(trucks, f.location, id), heading: 0,
      health: "idle", status: `Available in ${f.location}`, statusShort: `Available from ${f.truckAvailableAt}`, pill: "Available",
      location: f.location, truckAvailableAt: f.truckAvailableAt, currentTripId: null, costPerMile: d.data.carrier.costPerMile, opStatus: "Active", ...meta(),
    };
    return { id, title: `Truck ${f.unit} · ${f.driverName.trim()}`, link: { type: "truck", id } };
  },
  driver(d, f) {
    d.data.seq += 1;
    const id = `D-${d.data.seq}`;
    d.data.drivers[id] = { id, name: f.name.trim(), phone: f.phone, truckId: null, availableAt: f.availableAt, homeLocation: f.homeLocation, preferences: "", dutyNote: "Added via intake", ...meta() };
    if (f.truckId) {
      relinkDriver(d.data, d.data.drivers[id], f.truckId);
      d.data.drivers[id].truckId = f.truckId;
    }
    return { id, title: f.name.trim(), link: f.truckId ? { type: "truck", id: f.truckId } : null };
  },
  trip(d, f) {
    if (d.data.trips[f.id]) return null;
    const pw = formatWindow(f.pickupWindow);
    const dw = formatWindow(f.deliveryWindow);
    const t = {
      id: f.id, truckId: f.truckId, origin: f.origin, destination: f.destination, status: "confirmed", phase: "Confirmed", protected: !!f.protected,
      revenue: Number(f.revenue), loadedMiles: roadMiles(f.origin, f.destination), emptyMiles: 10, sortKey: 0, broker: f.broker,
      commodity: "", weight: null, pickup: { place: f.origin, window: pw }, delivery: { place: f.destination, window: dw }, routes: [],
      stops: [{ type: "pickup", coord: CITY_COORDS[f.origin], label: "" }, { type: "delivery", coord: CITY_COORDS[f.destination], label: "" }], ...meta(),
    };
    syncTrip(t);
    d.data.trips[t.id] = t;
    return { id: t.id, title: `${t.id} · ${f.origin} → ${f.destination}`, link: { type: "truck", id: f.truckId } };
  },
  carrier(d, f) {
    d.data.seq += 1;
    const id = `CAR-${d.data.seq}`;
    d.data.carriers[id] = {
      id, name: f.name.trim(), contactName: f.contactName, phone: f.phone, email: "", homeBase: f.homeBase, preferredLanes: "",
      maxDeadhead: Number(f.maxDeadhead), minRatePerMile: Number(f.minRatePerMile), avoidRegions: "", costPerMile: d.data.carrier.costPerMile, ...meta(),
    };
    return { id, title: f.name.trim(), link: null };
  },
};

export function createFromIntake(d, kind, form, events) {
  const r = CREATE[kind](d, form);
  if (!r) return false;
  log(d, `intake-${r.id}`, { source: "dispatcher", text: `Added ${r.title} via guided intake`, link: r.link });
  notify(d, `intake-${r.id}`, { group: "updates", title: "Fleet record added", body: r.title, link: r.link });
  events.push({ kind: "success", title: "Saved", body: `${r.title} added`, link: r.link });
  return true;
}

export const SETTING_LABEL = { negotiationFloor: "Negotiation floor", maxCounterSteps: "Max counter steps", autoContactBrokers: "Auto-contact brokers", driverTone: "Driver message tone" };
const fmt = (k, v) => (k === "negotiationFloor" ? `$${Number(v).toFixed(2)}/mi` : typeof v === "boolean" ? (v ? "On" : "Off") : String(v));

export function updateSetting(d, key, value) {
  const s = d.data.settings;
  if (key === "requireApproval" || !(key in SETTING_LABEL) || s[key] === value) return false;
  const old = s[key];
  s[key] = value;
  d.data.seq += 1;
  log(d, `setting-${d.data.seq}`, { source: "dispatcher", text: `AI setting · ${SETTING_LABEL[key]}: ${fmt(key, old)} → ${fmt(key, value)}`, link: { type: "activity", id: null } });
  return true;
}

export function toggleRule(d, id) {
  const r = d.data.rules[id];
  if (!r) return false;
  r.status = r.status === "inactive" ? "active" : "inactive";
  d.data.seq += 1;
  log(d, `rule-toggle-${d.data.seq}`, { source: "dispatcher", text: `AI rule ${r.status === "active" ? "re-enabled" : "turned off"}: ${r.text}`, link: { type: "rules", id: null } });
  return true;
}

export function deleteRule(d, id) {
  const r = d.data.rules[id];
  if (!r) return false;
  delete d.data.rules[id];
  d.data.seq += 1;
  log(d, `rule-delete-${d.data.seq}`, { source: "dispatcher", text: `AI rule deleted: ${r.text}`, link: { type: "rules", id: null } });
  return true;
}
