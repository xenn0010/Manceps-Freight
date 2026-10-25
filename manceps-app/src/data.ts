// Shared view types and constants. Demo-only data lives in src/demo/.

export type Tone = "grey" | "amber" | "green";
export type SheetTab = "loads" | "drivers";
export type LngLat = [number, number];
export type Fact = [string, string];

/** A spreadsheet row; every column value is a string, number or flag. */
export type Row = Record<string, string | number | boolean>;

/** Column definition: key, header, width in px, optional alignment ("c" | "r"). */
export type Column = [string, string, number, ("c" | "r")?];

/** Drivers sheet columns. Rows come from /v1/drivers; "checkin" and "notes" are written by the demo agent only. */
export const DCOLS: Column[] = [["driver", "Driver", 150], ["truck", "Truck", 90, "c"], ["carrier", "Carrier", 170], ["phone", "Phone", 140], ["email", "Email", 200], ["duty", "Status", 100], ["license", "License state", 110, "c"], ["licenseExp", "License expires", 130], ["checkin", "Last check-in", 150], ["notes", "Notes", 260]];

/** Columns the demo agent writes; they are not stored by the backend and carry a Demo tag. */
export const AGENT_COLUMNS: ReadonlySet<string> = new Set(["checkin", "notes"]);

/** Pill colors [background, ink] for status and duty cells. */
export const STATUS: Record<string, [string, string]> = {
  "In transit": ["rgba(34,114,173,.14)", "#1B5E94"],
  Delivered: ["rgba(1,13,29,.06)", "#3D4A5C"],
  "Needs your yes": ["#2272AD", "#FFFFFF"],
  Booked: ["rgba(31,154,90,.15)", "#17673E"],
  "Rate con sent": ["rgba(31,154,90,.15)", "#17673E"],
  Proposed: ["rgba(76,155,255,.16)", "#1B5E94"],
  Offer: ["rgba(1,13,29,.06)", "#3D4A5C"],
  Open: ["rgba(227,154,45,.18)", "#8A5A12"],
  Driving: ["rgba(34,114,173,.14)", "#1B5E94"],
  "On duty": ["rgba(31,154,90,.15)", "#17673E"],
  "Off duty": ["rgba(1,13,29,.06)", "#3D4A5C"],
  Active: ["rgba(31,154,90,.15)", "#17673E"],
  Inactive: ["rgba(1,13,29,.06)", "#3D4A5C"],
};

export const LETTERS = "ABCDEFGHIJKLMNOP";

export const TONE: Record<Tone, [string, string]> = {
  grey: ["#F1F5F9", "#3D4A5C"],
  amber: ["rgba(227,154,45,.16)", "#8A5A12"],
  green: ["rgba(31,154,90,.14)", "#17673E"],
};
