import { describe, expect, it } from "vitest";
import type { Carrier, Driver, Firm, Me, Truck } from "../api/types";
import { carrierLabel, driverPatchFor, isEditableDriverColumn, toDriverRows, toProfile, toTruckViews } from "./mappers";
import { keepAgentCells } from "./fleet";
import { mappingProblems } from "./imports";

const T0 = "2026-10-01T00:00:00Z";

const carrier = (id: string, patch: Partial<Carrier> = {}): Carrier => ({
  id, phone: "+14155550142", name: null, company: null, mc_number: null, dot_number: null, email: null, equipment: [], home_base: null,
  preferred_lanes: [], avoid: [], notes: null, status: "active", tags: [], insurance_expires_at: null, dispatch_fee_pct: null,
  rate_floor_per_mile: null, agreement_signed: null, consent: null, created_at: T0, updated_at: T0, ...patch,
});

const truck = (id: string, carrierId: string, unit: string, patch: Partial<Truck> = {}): Truck => ({
  id, carrier_id: carrierId, unit, equipment: null, vin: null, plate: null, plate_state: null, max_weight_lbs: null, created_at: T0, updated_at: T0, ...patch,
});

const driver = (id: string, carrierId: string, name: string | null, patch: Partial<Driver> = {}): Driver => ({
  id, carrier_id: carrierId, name, phone: null, email: null, status: "active", license_state: null, license_expires_at: null, consent: null, created_at: T0, updated_at: T0, ...patch,
});

const CARRIERS = [carrier("c1", { company: "Reed Hauling LLC", name: "Ava Reed" }), carrier("c2", { phone: "+15595550177" })];
const TRUCKS = [truck("t3", "c2", "103"), truck("t1", "c1", "101", { equipment: "dry_van", plate: "8ABC123", plate_state: "CA", max_weight_lbs: 45000, vin: "1FUJ" }), truck("t10", "c1", "10")];
const DRIVERS = [driver("d2", "c2", "Ben Ortiz", { status: "inactive", phone: "+15595550177", license_expires_at: "2027-03-31T00:00:00Z", license_state: "CA" }), driver("d1", "c1", "Ava Reed", { email: "ava@reed.test" })];

describe("carrierLabel", () => {
  it("prefers company, then name, then the formatted phone", () => {
    expect(carrierLabel(CARRIERS[0])).toBe("Reed Hauling LLC");
    expect(carrierLabel(carrier("x", { name: "Ben" }))).toBe("Ben");
    expect(carrierLabel(CARRIERS[1])).toBe("(559) 555-0177");
    expect(carrierLabel(undefined)).toBe("Unknown carrier");
  });
});

describe("toTruckViews", () => {
  it("sorts by unit number naturally and attaches the carrier's drivers", () => {
    const v = toTruckViews(TRUCKS, CARRIERS, DRIVERS);
    expect(v.map((t) => t.unit)).toEqual(["10", "101", "103"]);
    expect(v[1]).toEqual({
      id: "t1", unit: "101", equipment: "Dry van", plate: "8ABC123 · CA", vin: "1FUJ", maxWeight: "45,000 lb", carrierId: "c1", carrier: "Reed Hauling LLC",
      drivers: [{ id: "d1", name: "Ava Reed", phone: "", status: "Active" }],
    });
    expect(v[2]).toMatchObject({ equipment: "", plate: "", maxWeight: "", carrier: "(559) 555-0177", drivers: [{ name: "Ben Ortiz", phone: "(559) 555-0177", status: "Inactive" }] });
  });

  it("returns nothing for a brand-new firm", () => {
    expect(toTruckViews([], [], [])).toEqual([]);
  });
});

describe("toDriverRows", () => {
  it("maps drivers to sheet rows sorted by name, with the backend id and empty agent cells", () => {
    expect(toDriverRows(DRIVERS, CARRIERS, TRUCKS)).toEqual([
      { id: "d1", driver: "Ava Reed", truck: "10, 101", carrier: "Reed Hauling LLC", phone: "", email: "ava@reed.test", duty: "Active", license: "", licenseExp: "", checkin: "", notes: "" },
      { id: "d2", driver: "Ben Ortiz", truck: "103", carrier: "(559) 555-0177", phone: "(559) 555-0177", email: "", duty: "Inactive", license: "CA", licenseExp: "2027-03-31", checkin: "", notes: "" },
    ]);
  });

  it("keeps the demo agent's cells when rows are re-mapped", () => {
    const prev = [{ id: "d1", driver: "Ava", notes: "Texted", checkin: "Just now" }];
    const next = toDriverRows(DRIVERS, CARRIERS, TRUCKS);
    expect(keepAgentCells(next, prev)[0]).toMatchObject({ id: "d1", notes: "Texted", checkin: "Just now", driver: "Ava Reed" });
    expect(keepAgentCells(next, prev)[1]).toMatchObject({ notes: "", checkin: "" });
  });
});

describe("toProfile", () => {
  const firm: Firm = { id: "f1", name: "Acme Dispatch", slug: "acme", status: "active", plan: "trial", timezone: "America/Los_Angeles", owner_user_id: "u1", created_at: T0 };
  const me = (name: string | null, email: string | null): Me => ({
    user: { id: "u1", phone: "+12145550199", email, email_verified: false, name, status: "active" },
    memberships: [{ tenant_id: "acme", firm_name: "Acme Dispatch", role: "owner" }], current: { tenant_id: "acme", role: "owner" }, session_id: "s1",
  });

  it("builds the account header and rows from /v1/me and /v1/firm", () => {
    expect(toProfile(me("Jordan Diaz", "jordan@acme.test"), firm, { trucks: 1, drivers: 2 })).toEqual({
      name: "Jordan Diaz", initials: "JD", subtitle: "Acme Dispatch · Owner",
      rows: [["Company", "Acme Dispatch"], ["Phone", "(214) 555-0199"], ["Email", "jordan@acme.test"], ["Fleet", "1 truck · 2 drivers"], ["Time zone", "America/Los_Angeles"], ["Plan", "Trial"]],
    });
  });

  it("falls back to the phone when the user has no name, and says what is not set", () => {
    const p = toProfile(me(null, null), firm, { trucks: 0, drivers: 0 });
    expect(p).toMatchObject({ name: "(214) 555-0199", initials: "ME" });
    expect(p.rows).toContainEqual(["Email", "Not set"]);
    expect(p.rows).toContainEqual(["Fleet", "0 trucks · 0 drivers"]);
  });
});

describe("driverPatchFor", () => {
  it.each([
    ["driver", " Ava Reed ", { name: "Ava Reed" }],
    ["phone", "(415) 555-0142", { phone: "+14155550142" }],
    ["phone", "", { phone: null }],
    ["email", "ava@reed.test", { email: "ava@reed.test" }],
    ["duty", "Inactive", { status: "inactive" }],
    ["license", "ca", { license_state: "CA" }],
    ["licenseExp", "2027-03-31", { license_expires_at: "2027-03-31T00:00:00Z" }],
    ["licenseExp", "", { license_expires_at: null }],
  ])("%s %j -> patch", (k, v, patch) => {
    expect(driverPatchFor(k, v)).toEqual({ ok: true, patch });
  });

  it.each([["driver", ""], ["phone", "555"], ["email", "nope"], ["duty", "Driving"], ["licenseExp", "03/31/2027"], ["truck", "101"], ["carrier", "x"], ["notes", "hi"], ["checkin", "now"]])("refuses %s %j", (k, v) => {
    expect(driverPatchFor(k, v).ok).toBe(false);
  });

  it("only lets the backend's driver fields be edited", () => {
    expect(["driver", "phone", "email", "duty", "license", "licenseExp"].every(isEditableDriverColumn)).toBe(true);
    expect(["truck", "carrier", "checkin", "notes", "id"].some(isEditableDriverColumn)).toBe(false);
  });
});

describe("mappingProblems", () => {
  it("requires the natural keys and names each import needs", () => {
    expect(mappingProblems("carriers", { Cell: "phone", Name: "name" })).toEqual([]);
    expect(mappingProblems("carriers", { Name: "name" })).toEqual(["Pick the column with the carrier's phone."]);
    expect(mappingProblems("drivers", { "Carrier Cell": "carrier_phone", First: "first_name" })).toEqual([]);
    expect(mappingProblems("drivers", { Phone: "phone" })).toHaveLength(2);
    expect(mappingProblems("carriers", { A: "phone", B: "phone" })[0]).toMatch(/one column only/);
  });
});
