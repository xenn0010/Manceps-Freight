// Import flow helpers: which fields each entity accepts, the starting mapping, required-field checks, polling.
import type { ImportOut, ImportStatus } from "../api/types";

/** Entities the backend imports that this app offers (trucks have no import; they are added one by one). */
export type AppImportEntity = "carriers" | "drivers";

export const IMPORT_ENTITIES: [AppImportEntity, string][] = [["carriers", "Carriers"], ["drivers", "Drivers"]];

/** Field key and label per entity, from backend manceps_api/imports/schema.py. */
export const IMPORT_FIELDS: Record<AppImportEntity, [string, string][]> = {
  carriers: [["phone", "Phone"], ["name", "Name"], ["first_name", "First name"], ["last_name", "Last name"], ["company", "Company"], ["mc_number", "MC number"], ["dot_number", "DOT number"], ["email", "Email"], ["equipment", "Equipment"], ["home_base", "Home base"], ["notes", "Notes"], ["status", "Status"], ["tags", "Tags"], ["insurance_expires_at", "Insurance expires"], ["dispatch_fee_pct", "Dispatch fee %"], ["rate_floor_per_mile", "Rate floor per mile"], ["agreement_signed", "Agreement signed"]],
  drivers: [["carrier_phone", "Carrier phone"], ["name", "Name"], ["first_name", "First name"], ["last_name", "Last name"], ["phone", "Phone"], ["email", "Email"], ["status", "Status"], ["license_state", "License state"], ["license_expires_at", "License expires"]],
};

/** Statuses after which polling stops. */
const SETTLED: ReadonlySet<string> = new Set<ImportStatus>(["uploaded", "mapped", "committed", "failed", "undone"]);
export const IMPORT_POLL_MS = 1500;
/** Give up waiting after this many polls (about five minutes). */
export const IMPORT_POLL_LIMIT = 200;

/**
 * The mapping to start the mapping step with: the saved mapping, else the server's suggestion.
 *
 * Args:
 *   imp: The import.
 *
 * Returns:
 *   Column header -> field (null means "don't import").
 */
export function initialMapping(imp: ImportOut): Record<string, string | null> {
  const base = Object.keys(imp.mapping).length ? imp.mapping : imp.suggested_mapping;
  return Object.fromEntries(imp.columns.map((c) => [c, base[c] ?? null]));
}

/**
 * What still blocks a mapping, mirroring the backend's required fields.
 *
 * Args:
 *   entity: Carriers or drivers.
 *   mapping: Column -> field.
 *
 * Returns:
 *   Problems for the user; empty when the mapping can be sent.
 */
export function mappingProblems(entity: AppImportEntity, mapping: Record<string, string | null>): string[] {
  const used = Object.values(mapping).filter((v): v is string => Boolean(v));
  const out: string[] = [];
  const twice = used.filter((v, i) => used.indexOf(v) !== i);
  if (twice.length) out.push("Each field can come from one column only (" + [...new Set(twice)].join(", ") + ").");
  if (entity === "carriers" && !used.includes("phone")) out.push("Pick the column with the carrier's phone.");
  if (entity === "drivers") {
    if (!used.includes("carrier_phone")) out.push("Pick the column with the carrier's phone for each driver.");
    if (!used.some((v) => v === "name" || v === "first_name" || v === "last_name")) out.push("Pick the column with the driver's name.");
  }
  return out;
}

/**
 * Whether an import has stopped moving (needs the user, finished or failed).
 *
 * Args:
 *   status: Import status.
 *
 * Returns:
 *   True when polling should stop.
 */
export function isSettled(status: string): boolean {
  return SETTLED.has(status);
}

/**
 * Poll an import until it settles.
 *
 * Args:
 *   get: Loads the import by id.
 *   id: Import id.
 *   sleep: Wait function.
 *   onTick: Called with every intermediate state, for progress.
 *
 * Returns:
 *   The settled import.
 *
 * Raises:
 *   Error: When it does not settle within IMPORT_POLL_LIMIT polls.
 */
export async function waitForImport(get: (id: string) => Promise<ImportOut>, id: string, sleep: (ms: number) => Promise<void>, onTick?: (imp: ImportOut) => void): Promise<ImportOut> {
  for (let i = 0; i < IMPORT_POLL_LIMIT; i++) {
    const imp = await get(id);
    if (isSettled(imp.status)) return imp;
    onTick?.(imp);
    await sleep(IMPORT_POLL_MS);
  }
  throw new Error("The import is still running. Check back in a few minutes.");
}
