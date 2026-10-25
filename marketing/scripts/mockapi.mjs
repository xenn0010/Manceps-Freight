// A tiny in-browser stand-in for the Manceps API so the prebuilt app runs on demo data with no backend.
// Every phone number is a fictional (555) number; names match the app's own demo fleet.
const API = process.env.MANCEPS_API_URL ?? "http://127.0.0.1:8000";
const NOW = "2026-10-20T15:00:00Z";
const TENANT = "tn_demo_westbound";
const USER = "us_demo_jordan";

const FLEET = [
  ["101", "Ava Reed", "+14155550142", "Reed Trucking LLC", "dry_van", "CA"],
  ["102", "Ben Ortiz", "+15595550177", "Ortiz Freight", "reefer", "CA"],
  ["103", "Chloe Chen", "+19165550109", "Chen Transport", "flatbed", "CA"],
  ["104", "Daniel Brooks", "+14085550163", "Brooks Hauling", "dry_van", "CA"],
];

const stamp = { created_at: NOW, updated_at: NOW };
const carriers = FLEET.map(([unit, name, phone, company, eq, st]) => ({
  id: "ca_" + unit, phone, name, company, mc_number: null, dot_number: null, email: null, equipment: [eq], home_base: null,
  preferred_lanes: [], avoid: [], notes: null, status: "active", tags: [], insurance_expires_at: null, dispatch_fee_pct: 8,
  rate_floor_per_mile: 3.6, agreement_signed: true, consent: { sms: true, voice: true, whatsapp: true, method: "web", recorded_at: NOW }, ...stamp, _st: st,
})).map(({ _st, ...c }) => c);
const trucks = FLEET.map(([unit, , , , eq]) => ({ id: "tr_" + unit, carrier_id: "ca_" + unit, unit, equipment: eq, vin: null, plate: null, plate_state: null, max_weight_lbs: 80000, ...stamp }));
const drivers = FLEET.map(([unit, name, phone, , , st]) => ({
  id: "dr_" + unit, carrier_id: "ca_" + unit, name, phone, email: null, status: unit === "104" ? "inactive" : "active",
  license_state: st, license_expires_at: "2028-03-31", consent: { sms: true, voice: true, whatsapp: true, method: "web", recorded_at: NOW }, ...stamp,
}));
const token = { access_token: "demo-access-token", expires_in: 3600, refresh_token: null, session_id: "se_demo", user_id: USER, tenant_id: TENANT, role: "owner", state: "active", token_type: "bearer" };
const me = { user: { id: USER, phone: "+14155550100", email: null, email_verified: false, name: "Jordan Diaz", status: "active" }, memberships: [{ tenant_id: TENANT, firm_name: "Westbound Dispatch", role: "owner" }], current: { tenant_id: TENANT, role: "owner" }, session_id: "se_demo" };
const firm = { id: TENANT, name: "Westbound Dispatch", slug: "westbound", status: "active", plan: "pro", timezone: "America/Los_Angeles", owner_user_id: USER, created_at: NOW };
const page = (items) => ({ items, next_cursor: null });

const ROUTES = {
  "POST /v1/auth/refresh": token,
  "POST /v1/auth/switch-firm": token,
  "GET /v1/me": me,
  "GET /v1/firm": firm,
  "GET /v1/firm/provisioning": { status: "ready", tenant_id: TENANT, message: null },
  "GET /v1/trucks": page(trucks),
  "GET /v1/drivers": page(drivers),
  "GET /v1/carriers": page(carriers),
};

/**
 * Serve the demo API to every page in a browser context.
 *
 * Args:
 *   context: Playwright BrowserContext.
 *   appOrigin: Origin of the app, echoed in CORS headers.
 */
export async function installMockApi(context, appOrigin) {
  const cors = { "Access-Control-Allow-Origin": appOrigin, "Access-Control-Allow-Credentials": "true", "Access-Control-Allow-Headers": "authorization,content-type,idempotency-key", "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS" };
  await context.route(API + "/**", async (route) => {
    const req = route.request();
    if (req.method() === "OPTIONS") return route.fulfill({ status: 204, headers: cors });
    const path = new URL(req.url()).pathname;
    const body = ROUTES[req.method() + " " + path];
    if (body === undefined) {
      console.warn("[mockapi] unhandled", req.method(), path);
      return route.fulfill({ status: 404, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify({ error: { code: "not_found", message: "Not in the demo" } }) });
    }
    return route.fulfill({ status: 200, headers: { ...cors, "Content-Type": "application/json" }, body: JSON.stringify(body) });
  });
}
