import { CITIES } from "./cities";
import { formatWindow, windowError, windowForm } from "./windows";

export const EQUIPMENT = ["53' dry van", "53' reefer", "48' flatbed"];
const opts = (list) => list.map((v) => [v, v]);
const truckOpts = (data) => Object.values(data.trucks).map((t) => [t.id, `Truck ${t.unit}`]);
const cityOpts = () => opts(CITIES);
const carrierOpts = (data) => [data.carrier, ...Object.values(data.carriers)].map((c) => [c.id, c.name]);
const email = (v) => (v && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v) ? "Enter a valid email" : null);
const unitCheck = (v, { data, id }) =>
  !/^\d{3,4}$/.test(v) ? "Use a 3–4 digit unit" : Object.values(data.trucks).some((t) => t.unit === v && t.id !== id) ? `Truck ${v} already exists` : null;

export const FIELDS = {
  carrier: [
    { key: "name", label: "Carrier name", required: true },
    { key: "contactName", label: "Contact name" },
    { key: "phone", label: "Phone" },
    { key: "email", label: "Email", validate: email },
    { key: "homeBase", label: "Home base", section: "Operating preferences" },
    { key: "preferredLanes", label: "Preferred lanes" },
    { key: "maxDeadhead", label: "Max deadhead (mi)", kind: "number", required: true },
    { key: "minRatePerMile", label: "Min rate ($/mi)", kind: "number", required: true },
    { key: "avoidRegions", label: "Avoid regions" },
  ],
  truck: [
    { key: "unit", label: "Unit", required: true, validate: unitCheck },
    { key: "carrierId", label: "Carrier", kind: "select", required: true, options: carrierOpts },
    { key: "equipment", label: "Equipment", kind: "select", required: true, options: () => opts(EQUIPMENT) },
    { key: "location", label: "Current location", required: true },
    { key: "opStatus", label: "Operational status", kind: "select", required: true, options: () => opts(["Active", "Out of service"]) },
    { key: "truckAvailableAt", label: "Truck availability (from)", required: true, section: "Availability" },
    { key: "costPerMile", label: "Cost ($/mi)", kind: "number", required: true, section: "Cost assumptions", hint: "Default $1.80 · applies to this truck's trips and segments" },
  ],
  driver: [
    { key: "name", label: "Driver name", required: true },
    { key: "phone", label: "Phone" },
    { key: "truckId", label: "Assigned truck", kind: "select", options: (data, rec) => [...(rec?.truckId ? [] : [["", "Unassigned"]]), ...truckOpts(data)] },
    { key: "availableAt", label: "Driver availability (from)", required: true, section: "Availability" },
    { key: "homeLocation", label: "Home location" },
    { key: "preferences", label: "Preferences", kind: "textarea" },
  ],
  trip: [
    { key: "truckId", label: "Truck", kind: "select", required: true, options: truckOpts },
    { key: "origin", label: "Origin", required: true },
    { key: "destination", label: "Destination", required: true },
    { key: "pickupWindow", path: "pickup.window", label: "Pickup window", kind: "window", required: true, section: "Windows" },
    { key: "deliveryWindow", path: "delivery.window", label: "Delivery window", kind: "window", required: true },
    { key: "status", label: "Status", kind: "select", required: true, options: () => [["active", "Active"], ["confirmed", "Confirmed"], ["cancelled", "Cancelled"]], section: "Terms" },
    { key: "revenue", label: "Rate ($)", kind: "number", required: true },
    { key: "broker", label: "Broker" },
    { key: "commodity", label: "Commodity" },
    { key: "weight", label: "Weight (lb)", kind: "number" },
    { key: "protected", label: "Protected commitment", kind: "check" },
  ],
};

export const INTAKE_FIELDS = {
  carrier: [
    { key: "name", label: "Carrier name", required: true, validate: (v, { data }) => ([data.carrier, ...Object.values(data.carriers)].some((c) => c.name.toLowerCase() === v.toLowerCase()) ? `${v} already exists` : null) },
    { key: "contactName", label: "Contact name" },
    { key: "phone", label: "Phone" },
    { key: "homeBase", label: "Home base", kind: "select", options: cityOpts },
    { key: "maxDeadhead", label: "Max deadhead (mi)", kind: "number", required: true },
    { key: "minRatePerMile", label: "Min rate ($/mi)", kind: "number", required: true },
  ],
  truck: [
    { key: "unit", label: "Unit", required: true, validate: unitCheck },
    { key: "equipment", label: "Equipment", kind: "select", required: true, options: () => opts(EQUIPMENT) },
    { key: "location", label: "Location", kind: "select", required: true, options: cityOpts },
    { key: "truckAvailableAt", label: "Truck availability", required: true, placeholder: "e.g. Tue 06:00" },
    { key: "driverName", label: "Driver name", required: true },
    { key: "driverPhone", label: "Driver phone" },
    { key: "driverAvailableAt", label: "Driver availability", required: true, placeholder: "e.g. Tue 06:00" },
  ],
  driver: [
    { key: "name", label: "Driver name", required: true },
    { key: "phone", label: "Phone" },
    { key: "truckId", label: "Assigned truck", kind: "select", options: (data) => [["", "Unassigned"], ...truckOpts(data)] },
    { key: "availableAt", label: "Driver availability", required: true, placeholder: "e.g. Tue 08:00" },
    { key: "homeLocation", label: "Home location", kind: "select", options: cityOpts },
  ],
  trip: [
    { key: "id", label: "Load ID", required: true, validate: (v, { data }) => (!/^L-\d{3}$/.test(v) ? "Use L-123" : data.trips[v] ? `${v} already exists` : null) },
    { key: "truckId", label: "Truck", kind: "select", required: true, options: truckOpts },
    { key: "origin", label: "Origin", kind: "select", required: true, options: cityOpts },
    { key: "destination", label: "Destination", kind: "select", required: true, options: cityOpts, validate: (v, { form }) => (v && v === form.origin ? "Must differ from origin" : null) },
    { key: "pickupWindow", label: "Pickup window", kind: "window", required: true },
    { key: "deliveryWindow", label: "Delivery window", kind: "window", required: true },
    { key: "revenue", label: "Rate ($)", kind: "number", required: true },
    { key: "broker", label: "Broker" },
    { key: "protected", label: "Protected commitment", kind: "check" },
  ],
};

const getPath = (rec, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), rec);

export function toForm(type, rec) {
  const f = {};
  FIELDS[type].forEach((fd) => {
    const v = getPath(rec, fd.path || fd.key);
    f[fd.key] = fd.kind === "window" ? windowForm(v) : fd.kind === "check" ? !!v : v == null ? "" : String(v);
  });
  return f;
}

export function toPatch(type, form, rec) {
  const patch = {};
  FIELDS[type].forEach((fd) => {
    const raw = form[fd.key];
    const v = fd.kind === "window" ? (raw.text !== undefined ? raw.text : formatWindow(raw)) : fd.kind === "number" ? (raw === "" ? null : Number(raw)) : raw;
    if (fd.path) {
      const [a, b] = fd.path.split(".");
      patch[a] = { ...(patch[a] || rec[a]), [b]: v };
    } else patch[fd.key] = v;
  });
  return patch;
}

export function validate(fields, form, ctx) {
  const errors = {};
  fields.forEach((fd) => {
    const v = form[fd.key];
    let e = null;
    if (fd.kind === "window") e = windowError(v, fd.required);
    else if (fd.kind === "check") e = null;
    else if (v === "" || v == null || (typeof v === "string" && !v.trim())) e = fd.required ? "Required" : null;
    else if (fd.kind === "number" && !(Number(v) > 0)) e = "Enter a positive number";
    if (!e && fd.validate && v !== "" && v != null) e = fd.validate(v, { ...ctx, form });
    if (e) errors[fd.key] = e;
  });
  return errors;
}
