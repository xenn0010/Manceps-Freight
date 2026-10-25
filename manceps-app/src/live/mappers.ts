// Map API shapes to the rows and views the screens render, and sheet edits back to API patches.
import type { Carrier, Driver, DriverPatch, Firm, Me, Truck } from "../api/types";
import { formatUsPhone, normalizeUsPhone } from "../auth/phone";
import type { Fact, Row } from "../data";
import { nameParts } from "../logic/derive";

export interface DriverLite {
  id: string;
  name: string;
  phone: string;
  status: string;
}

export interface TruckView {
  id: string;
  unit: string;
  equipment: string;
  plate: string;
  vin: string;
  maxWeight: string;
  carrierId: string;
  carrier: string;
  drivers: DriverLite[];
}

export interface ProfileView {
  name: string;
  initials: string;
  subtitle: string;
  rows: Fact[];
}

const ISO_DATE_LEN = 10;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const NAME_MAX = 200;
const LICENSE_STATE_MAX = 16;
const NOT_SET = "Not set";

/**
 * Human label for a carrier: company, else contact name, else phone.
 *
 * Args:
 *   c: Carrier, or undefined when it is unknown.
 *
 * Returns:
 *   A non-empty label.
 */
export function carrierLabel(c: Carrier | undefined): string {
  if (!c) return "Unknown carrier";
  return c.company || c.name || (c.phone ? formatUsPhone(c.phone) : "Carrier");
}

/** "dry_van" -> "Dry van"; empty for null. */
export function equipmentLabel(code: string | null): string {
  if (!code) return "";
  const s = code.replace(/[_-]+/g, " ").trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "active" -> "Active"; the backend status for the Status column. */
export function statusLabel(status: string): string {
  return status ? status.charAt(0).toUpperCase() + status.slice(1) : "";
}

function driverLite(d: Driver): DriverLite {
  return { id: d.id, name: d.name ?? "", phone: d.phone ? formatUsPhone(d.phone) : "", status: statusLabel(d.status) };
}

function byUnit(a: { unit: string }, b: { unit: string }): number {
  return a.unit.localeCompare(b.unit, "en-US", { numeric: true });
}

/**
 * Build the truck list for the map, board and truck panel. Drivers attach through their carrier.
 *
 * Args:
 *   trucks: From /v1/trucks.
 *   carriers: From /v1/carriers.
 *   drivers: From /v1/drivers.
 *
 * Returns:
 *   Truck views sorted by unit number.
 */
export function toTruckViews(trucks: Truck[], carriers: Carrier[], drivers: Driver[]): TruckView[] {
  const cs = new Map(carriers.map((c) => [c.id, c]));
  return [...trucks].sort(byUnit).map((t) => ({
    id: t.id, unit: t.unit, equipment: equipmentLabel(t.equipment),
    plate: t.plate ? [t.plate, t.plate_state].filter(Boolean).join(" · ") : "",
    vin: t.vin ?? "", maxWeight: t.max_weight_lbs ? t.max_weight_lbs.toLocaleString("en-US") + " lb" : "",
    carrierId: t.carrier_id, carrier: carrierLabel(cs.get(t.carrier_id)),
    drivers: drivers.filter((d) => d.carrier_id === t.carrier_id).map(driverLite),
  }));
}

/**
 * Build drivers sheet rows. Truck lists the carrier's truck units; checkin and notes start empty (demo agent only).
 *
 * Args:
 *   drivers: From /v1/drivers.
 *   carriers: From /v1/carriers.
 *   trucks: From /v1/trucks.
 *
 * Returns:
 *   One row per driver, sorted by name, with the backend id under "id".
 */
export function toDriverRows(drivers: Driver[], carriers: Carrier[], trucks: Truck[]): Row[] {
  const cs = new Map(carriers.map((c) => [c.id, c]));
  const sorted = [...drivers].sort((a, b) => (a.name ?? "").localeCompare(b.name ?? ""));
  return sorted.map((d) => ({
    id: d.id, driver: d.name ?? "",
    truck: trucks.filter((t) => t.carrier_id === d.carrier_id).sort(byUnit).map((t) => t.unit).join(", "),
    carrier: carrierLabel(cs.get(d.carrier_id)), phone: d.phone ? formatUsPhone(d.phone) : "", email: d.email ?? "",
    duty: statusLabel(d.status), license: d.license_state ?? "",
    licenseExp: d.license_expires_at ? d.license_expires_at.slice(0, ISO_DATE_LEN) : "", checkin: "", notes: "",
  }));
}

/**
 * Account panel header and profile rows from /v1/me and /v1/firm.
 *
 * Args:
 *   me: The signed-in user.
 *   firm: The current firm.
 *   counts: Fleet size from the trucks and drivers lists.
 *
 * Returns:
 *   Display name, initials, "Firm · Role" subtitle and label/value rows.
 */
export function toProfile(me: Me, firm: Firm, counts: { trucks: number; drivers: number }): ProfileView {
  const phone = me.user.phone ? formatUsPhone(me.user.phone) : "";
  const name = me.user.name || phone || "You";
  const role = statusLabel(me.current.role);
  const initials = me.user.name ? nameParts(me.user.name).initials.slice(0, 2).toUpperCase() : "ME";
  const plural = (n: number, w: string): string => n + " " + w + (n === 1 ? "" : "s");
  return {
    name, initials, subtitle: firm.name + " · " + role,
    rows: [["Company", firm.name], ["Phone", phone || NOT_SET], ["Email", me.user.email ?? NOT_SET], ["Fleet", plural(counts.trucks, "truck") + " · " + plural(counts.drivers, "driver")], ["Time zone", firm.timezone], ["Plan", statusLabel(firm.plan)]],
  };
}

export type CellEdit = { ok: true; patch: DriverPatch } | { ok: false; error: string };

type Editor = (v: string) => CellEdit;

const ok = (patch: DriverPatch): CellEdit => ({ ok: true, patch });
const bad = (error: string): CellEdit => ({ ok: false, error });

/** Sheet column -> how a typed value becomes a DriverPatch. Columns not listed cannot be edited. */
const DRIVER_EDITORS: Record<string, Editor> = {
  driver: (v) => (v && v.length <= NAME_MAX ? ok({ name: v }) : bad("A driver needs a name (up to 200 characters).")),
  phone: (v) => {
    if (!v) return ok({ phone: null });
    const p = normalizeUsPhone(v);
    return p ? ok({ phone: p }) : bad("Enter a 10-digit US phone number.");
  },
  email: (v) => (!v ? ok({ email: null }) : EMAIL_RE.test(v) ? ok({ email: v }) : bad("Enter a valid email address.")),
  duty: (v) => {
    const s = v.toLowerCase();
    return s === "active" || s === "inactive" ? ok({ status: s }) : bad("Status is Active or Inactive.");
  },
  license: (v) => (v.length <= LICENSE_STATE_MAX ? ok({ license_state: v ? v.toUpperCase() : null }) : bad("Use the state code, like CA.")),
  licenseExp: (v) => (!v ? ok({ license_expires_at: null }) : DATE_RE.test(v) && !Number.isNaN(Date.parse(v)) ? ok({ license_expires_at: v + "T00:00:00Z" }) : bad("Use a date like 2027-03-31.")),
};

/**
 * Whether a drivers sheet column can be edited and saved to the backend.
 *
 * Args:
 *   key: Column key.
 *
 * Returns:
 *   True for name, phone, email, status, license state and license expiry.
 */
export function isEditableDriverColumn(key: string): boolean {
  return key in DRIVER_EDITORS;
}

/**
 * Turn a typed cell value into the PATCH /v1/drivers/{id} body, or explain why it is refused.
 *
 * Args:
 *   key: Column key.
 *   raw: Typed value.
 *
 * Returns:
 *   The patch, or an error message for the user.
 */
export function driverPatchFor(key: string, raw: string): CellEdit {
  const edit = DRIVER_EDITORS[key];
  if (!edit) return bad("This column can't be edited here.");
  return edit(raw.trim());
}
