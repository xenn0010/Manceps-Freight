// Live data: profile, trucks, drivers and carriers from the backend, driver cell saves and truck creation.
import { showToast } from "../actions";
import { data } from "../api";
import { friendlyMessage } from "../api/errors";
import type { Carrier, CarrierCreate, Driver, Firm, Me, Truck } from "../api/types";
import { AGENT_COLUMNS, type Row } from "../data";
import { getState, setState } from "../store";
import { driverPatchFor, toDriverRows, toProfile, toTruckViews } from "./mappers";

interface Cache {
  me: Me | null;
  firm: Firm | null;
  trucks: Truck[];
  drivers: Driver[];
  carriers: Carrier[];
}

const cache: Cache = { me: null, firm: null, trucks: [], drivers: [], carriers: [] };

/** Forget everything loaded for the previous session. */
export function clearLiveCache(): void {
  Object.assign(cache, { me: null, firm: null, trucks: [], drivers: [], carriers: [] });
}

/**
 * Carry the demo agent's cells (check-in, notes) over to freshly mapped rows with the same id.
 *
 * Args:
 *   next: Rows mapped from the API.
 *   prev: Rows currently on screen.
 *
 * Returns:
 *   next, with agent cells copied from prev.
 */
export function keepAgentCells(next: Row[], prev: Row[]): Row[] {
  const old = new Map(prev.map((r) => [r.id, r]));
  return next.map((r) => {
    const o = old.get(r.id);
    if (!o) return r;
    const kept: Row = { ...r };
    AGENT_COLUMNS.forEach((k) => { const v = o[k]; if (v !== undefined) kept[k] = v; });
    return kept;
  });
}

function publish(): void {
  const { me, firm, trucks, drivers, carriers } = cache;
  setState((s) => ({
    trucks: toTruckViews(trucks, carriers, drivers),
    carriers,
    drivers: keepAgentCells(toDriverRows(drivers, carriers, trucks), s.drivers),
    profile: me && firm ? toProfile(me, firm, { trucks: trucks.length, drivers: drivers.length }) : s.profile,
  }));
}

/** Load the profile and the whole fleet; the screens show loading, then data or an error. */
export async function loadAll(): Promise<void> {
  setState({ fleetStatus: "loading", fleetError: null });
  try {
    const [me, firm, trucks, drivers, carriers] = await Promise.all([data.me(), data.firm(), data.trucks(), data.drivers(), data.carriers()]);
    Object.assign(cache, { me, firm, trucks, drivers, carriers });
    publish();
    setState({ fleetStatus: "ready" });
  } catch (e) {
    setState({ fleetStatus: "error", fleetError: friendlyMessage(e) });
  }
}

/** Reload trucks, drivers and carriers, e.g. after an import or a new truck. */
export async function reloadFleet(): Promise<void> {
  try {
    const [trucks, drivers, carriers] = await Promise.all([data.trucks(), data.drivers(), data.carriers()]);
    Object.assign(cache, { trucks, drivers, carriers });
    publish();
    setState({ fleetStatus: "ready", fleetError: null });
  } catch (e) {
    showToast(friendlyMessage(e));
  }
}

/**
 * Save one drivers sheet cell with PATCH /v1/drivers/{id}. Columns the backend does not accept are refused.
 *
 * Args:
 *   r: Row index in the drivers sheet.
 *   k: Column key.
 *   value: Typed value.
 *
 * Returns:
 *   True when saved; false when refused or the request failed (a toast explains why).
 */
export async function saveDriverCell(r: number, k: string, value: string): Promise<boolean> {
  const row = getState().drivers[r];
  if (!row || typeof row.id !== "string") return false;
  const edit = driverPatchFor(k, value);
  if (!edit.ok) { showToast(edit.error); return false; }
  try {
    const updated = await data.patchDriver(row.id, edit.patch);
    cache.drivers = cache.drivers.map((d) => (d.id === updated.id ? updated : d));
    publish();
    setState((s) => ({ flash: { ...s.flash, ["drivers" + r + k]: Date.now() } }));
    return true;
  } catch (e) {
    showToast(friendlyMessage(e));
    return false;
  }
}

/** Idempotency keys for one "Add a truck" action; made when the form opens and reused on retries. */
export interface AddTruckKeys {
  carrier: string;
  truck: string;
  driver: string;
}

export interface AddTruckInput {
  /** Existing carrier id, or null to create newCarrier first. */
  carrierId: string | null;
  newCarrier: CarrierCreate | null;
  unit: string;
  equipment: string | null;
  plate: string | null;
  driverName: string | null;
  driverPhone: string | null;
}

/**
 * Create a truck (and, when asked, its carrier and first driver), then reload the fleet.
 *
 * Args:
 *   input: Validated form values.
 *   keys: Idempotency keys for this user action.
 *
 * Returns:
 *   The new truck.
 *
 * Raises:
 *   ApiError: When any create fails; earlier creates are kept and replay safely with the same keys.
 */
export async function addTruck(input: AddTruckInput, keys: AddTruckKeys): Promise<Truck> {
  let carrierId = input.carrierId;
  if (!carrierId) {
    if (!input.newCarrier) throw new Error("addTruck needs a carrier id or a new carrier");
    carrierId = (await data.createCarrier(input.newCarrier, keys.carrier)).id;
  }
  const truck = await data.createTruck({ carrier_id: carrierId, unit: input.unit, equipment: input.equipment, plate: input.plate }, keys.truck);
  if (input.driverName) await data.createDriver({ carrier_id: carrierId, name: input.driverName, phone: input.driverPhone, status: "active" }, keys.driver);
  await reloadFleet();
  return truck;
}
